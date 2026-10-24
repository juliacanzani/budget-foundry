import cv2,sys
k=sys.argv[1]; n=int(sys.argv[2])
im=cv2.cvtColor(cv2.imread(f'{k}_ink.png',0),cv2.COLOR_GRAY2BGR); im=255-im
H,W=im.shape[:2]
for y in range(0,H,50):
    c=(0,0,255) if y%100==0 else (255,180,180)
    cv2.line(im,(0,y),(W,y),c,2 if y%100==0 else 1)
    if y%100==0: cv2.putText(im,str(y),(5,y-5),cv2.FONT_HERSHEY_SIMPLEX,1.6,(0,0,255),3)
for x in range(0,W,500):
    cv2.line(im,(x,0),(x,H),(0,160,0),2); cv2.putText(im,str(x),(x+5,40),cv2.FONT_HERSHEY_SIMPLEX,1.4,(0,160,0),3)
for i in range(n):
    b=im[int(H*i/n):int(H*(i+1)/n)]
    s=1900/W; b=cv2.resize(b,None,fx=s,fy=s,interpolation=cv2.INTER_AREA)
    cv2.imwrite(f'ru_{k}{i}.jpg',b,[cv2.IMWRITE_JPEG_QUALITY,80])
