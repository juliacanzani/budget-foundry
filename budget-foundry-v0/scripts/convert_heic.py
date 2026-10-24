# Step 0: convert source HEICs to PNG. prep.py expects /home/claude/<name>.png — adjust paths there.
from pillow_heif import register_heif_opener; register_heif_opener()
from PIL import Image
import sys, os
src = sys.argv[1] if len(sys.argv) > 1 else '../sources'
dst = sys.argv[2] if len(sys.argv) > 2 else '..'
for f in ['IMG_3524', 'IMG_3521_2', 'IMG_3526', 'IMG_3531']:
    Image.open(os.path.join(src, f + '.heic')).save(os.path.join(dst, f + '.png'))
    print('converted', f)
