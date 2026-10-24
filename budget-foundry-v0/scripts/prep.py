import cv2, numpy as np, sys
sheets = {'A':'IMG_3524','B':'IMG_3521_2','C':'IMG_3526','D':'IMG_3531'}
for k,f in sheets.items():
    g = cv2.imread(f'/home/claude/{f}.png', cv2.IMREAD_GRAYSCALE).astype(np.float32)
    # background estimate: closing removes dark ink, then blur
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(81,81))
    bg = cv2.morphologyEx(g, cv2.MORPH_CLOSE, ker)
    bg = cv2.GaussianBlur(bg,(0,0),25)
    norm = np.clip(g/np.maximum(bg,1)*255,0,255).astype(np.uint8)
    cv2.imwrite(f'{k}_norm.png', norm)
    # ink = darker than 55% of local background, and page bg must be bright
    ink = ((norm < 140) & (bg > 120)).astype(np.uint8)*255
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((3,3),np.uint8))
    cv2.imwrite(f'{k}_ink.png', ink)
    print(k, g.shape)
