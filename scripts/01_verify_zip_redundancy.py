import zipfile,glob,os
base=r"D:\data science\AI Analytics System"
os.chdir(base)
mismatch=[];missing=[];total=0
for z in sorted(glob.glob('*.zip')):
    with zipfile.ZipFile(z) as f:
        for i in f.infolist():
            total+=1
            p=i.filename
            if not os.path.exists(p): missing.append((z,p)); continue
            if os.path.getsize(p)!=i.file_size: mismatch.append((z,p,os.path.getsize(p),i.file_size))
print("zip members:",total,"missing loose:",len(missing),"size mismatch:",len(mismatch))
for m in missing[:20]: print("MISSING",m)
for m in mismatch[:20]: print("MISMATCH",m)
