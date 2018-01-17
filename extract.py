import unitypack
import fsb5
from PIL import ImageOps,Image
import os,pickle,io,sys,locale
from unitypack.engine.texture import TextureFormat
from argparse import ArgumentParser
import subprocess

currentWorkDir=os.getcwd()

ETC_SERIES=(
	TextureFormat.ETC_RGB4,
	TextureFormat.ETC2_RGB,
	TextureFormat.ETC2_RGBA8,
	TextureFormat.ETC2_RGBA1,
	TextureFormat.EAC_R,
	TextureFormat.EAC_RG,
	TextureFormat.EAC_R_SIGNED,
	TextureFormat.EAC_RG_SIGNED,
)

def putTextFile(filename,directory,content,mode="wb",encoding="utf-8"):
	if(not(os.path.exists(directory))):
		os.makedirs(directory)

	path=os.path.join(directory,filename)

	with open(path,mode=mode,encoding=encoding) as file:
		print("Writing contents to "+path)
		file.write(content)
	return path

def putFile(filename,directory,content,mode="wb"):
	if(not(os.path.exists(directory))):
		os.makedirs(directory)

	path=os.path.join(directory,filename)

	with open(path,mode=mode) as file:
		print("Writing contents to "+path)
		file.write(content)
	return path

def readSamplesFromFSB5(fsb):
	for sample in fsb.samples:
		try:
			yield sample.name,fsb.rebuild_sample(sample)
		except ValueError as e:
			print('FAILED to extract %r: %s'%(sample.name,e))

def getPKMHeader(width,height,tformat):
	header=b"\x50\x4B\x4D\x20"

	version=b"20"
	if tformat==TextureFormat.ETC_RGB4:
		version=b"10"
		formatD=0
	elif tformat==TextureFormat.ETC2_RGB:
		formatD=1
	elif tformat==TextureFormat.ETC2_RGBA8:
		formatD=3
	elif tformat==TextureFormat.ETC2_RGBA1:
		formatD=4
	elif tformat==TextureFormat.EAC_R:
		formatD=5
	elif tformat==TextureFormat.EAC_RG:
		formatD=6
	elif tformat==TextureFormat.EAC_R_SIGNED:
		formatD=7
	elif tformat==TextureFormat.EAC_RG_SIGNED:
		formatD=8
	else:
		formatD=0

	formatB=formatD.to_bytes(2,byteorder="big")
	widthB=width.to_bytes(2,byteorder="big")
	heightB=height.to_bytes(2,byteorder="big")

	return(header+version+formatB+widthB+heightB+widthB+heightB)

class UnityGameResUnpack:

	apkExtractedPath="./orz/"
	assetsExtractTo="./assets/"

	def __init__(self,args):
		self.parseCmdArgs(args)

	def parseCmdArgs(self,args):
		parser=ArgumentParser()
		parser.add_argument("-o", "--outdir",nargs="?",default="",help="Directory where extracted files will be put",required=True)
		parser.add_argument("-i", "--indir",nargs="?",default="",help="Directory to parse",required=True)
		args=parser.parse_args(args)
		if(args.indir=='' or args.outdir==''):
			parser.print_help()
			exit()
		else:
			self.apkExtractedPath=args.indir
			self.assetsExtractTo=args.outdir
			print(args.indir,args.outdir)


	def handleFile(self,filepath):
		subdirname=filepath.replace(self.apkExtractedPath,"")
		while(subdirname[0]=="/" or subdirname[0]=="\\"):
			subdirname=subdirname[1:]
		savepath=os.path.join(self.assetsExtractTo,subdirname)
		os.makedirs(savepath,exist_ok=True)
		# savepath=os.path.dirname(filepath);
		with open(filepath,'rb') as file:
			bundle=unitypack.load(file)
			for asset in bundle.assets:
				for id,obj in asset.objects.items():
					try:
						data=obj.read()

						if obj.type=="AudioClip":
							print(obj.type,":",data.name)
							# extract samples
							bindata=data.data
							index=0
							while bindata:
								fsb=fsb5.load(bindata)
								ext=fsb.get_sample_extension()
								bindata=bindata[fsb.raw_size:]
								for sampleName,sampleData in readSamplesFromFSB5(fsb):
									filenameWrite=data.name+"--"+sampleName+'.'+ext
									putFile(filenameWrite,savepath,sampleData)
								index+=1
						
						elif obj.type=="Texture2D":
							print(obj.type+"["+str(data.format)+"]:",data.name)
							filename=data.name+".png"
							if data.format in ETC_SERIES:
								bindata=getPKMHeader(data.width,data.height,data.format)+data.image_data
								putFile('temp.pkm',currentWorkDir,bindata)
								subprocess.call(["./etcpack","./temp.pkm",currentWorkDir])
								image=Image.open('./temp.ppm')
							else:
								image=data.image
								if image is None:
									print("WARNING: %s is an empty image"%(filename))
									continue
							img=ImageOps.flip(image)
							output=io.BytesIO()
							img.save(output,format="png")
							putFile(filename,savepath,output.getvalue())

						elif obj.type=="MovieTexture":
							print(obj.type,":",data.name)
							filename=data.name+".ogv"
							putFile(filename,savepath,data.movie_data)

						# elif obj.type=="Shader":
						# 	print(obj.type,":",data.name)
						# 	filename=data.name+".cg"
						# 	putFile(filename,savepath,data.script)
						
						elif obj.type=="Mesh":
							print(obj.type,":",data.name)
							try:
								meshdata=unitypack.export.OBJMesh(d).export()
								filename=data.name+".obj"
								putFile(filename,savepath,meshdata)
							except NotImplementedError as e:
								print("WARNING: Could not extract %r (%s)"%(d,e))
								meshdata=pickle.dumps(data._obj)
								filename=data.name+".Mesh.pickle"
								putFile(filename,savepath,meshdata)
						
						elif obj.type=="Font":
							print(obj.type,":",data.name)
							filename=data.name+".ttf"
							putFile(filename,savepath,data.data)

						elif obj.type=="TextAsset":
							print(obj.type,":",data.name)
							if isinstance(data.script,bytes):
								filename,mode=data.name,"wb"
							else:
								filename,mode=data.name,"w"
							putTextFile(filename,savepath,data.script,mode=mode,encoding="utf-8")
					except Exception as e:
						print("WARNING: Error while processing %r (%s)"%(filepath,e))

def main():
	ugru=UnityGameResUnpack(sys.argv[1:])
	for currentPath,dirs,files in os.walk(ugru.apkExtractedPath):
		for nowFile in files:
			try:
				nowFilePath=os.path.join(currentPath,nowFile)
				with open(nowFilePath,'rb') as file:
					bundle=unitypack.load(file)
			except NotImplementedError as e:
				pass
			else:
				ugru.handleFile(nowFilePath)


if __name__=="__main__":
	main()
