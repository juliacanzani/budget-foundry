import cv2, numpy as np, json
from skimage.morphology import skeletonize
out={}
for k in 'ABCD':
    ink=cv2.imread(f'{k}_ink.png',0)
    H,W=ink.shape
    n,lab,st,cen=cv2.connectedComponentsWithStats(ink,8)
    dist=cv2.distanceTransform(ink,cv2.DIST_L2,5)
    comps=[]
    for i in range(1,n):
        x,y,w,h,a=st[i]
        if a<150: continue
        if x<=2 or y<=2 or x+w>=W-3 or y+h>=H-3: continue
        if w>W*0.3 or h>H*0.2: continue
        m=(lab[y:y+h,x:x+w]==i)
        sk=skeletonize(m)
        d=dist[y:y+h,x:x+w][sk]
        sw=float(np.median(d)*2) if d.size else 0
        comps.append(dict(id=int(i),x=int(x),y=int(y),w=int(w),h=int(h),a=int(a),sw=round(sw,1)))
    out[k]=comps
    sws=np.array([c['sw'] for c in comps])
    print(k,len(comps),'sw pct',np.percentile(sws,[5,25,50,75,95]).round(1))
    np.save(f'{k}_lab.npy',lab)
json.dump(out,open('comps.json','w'))
