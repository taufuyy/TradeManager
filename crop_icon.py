from PIL import Image

def analyze_and_crop(img_path, out_path):
    img = Image.open(img_path).convert("RGBA")
    
    # We want to crop the central part to remove any potential white borders completely.
    # Assuming the logo is centered, let's crop 10% from all sides.
    width, height = img.size
    crop_amount_w = int(width * 0.15)
    crop_amount_h = int(height * 0.15)
    
    cropped_img = img.crop((crop_amount_w, crop_amount_h, width - crop_amount_w, height - crop_amount_h))
    
    # Also ensure any outer pixels that are white/near-white are transparent
    data = cropped_img.getdata()
    new_data = []
    for item in data:
        if item[0] > 200 and item[1] > 200 and item[2] > 200:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
            
    cropped_img.putdata(new_data)
    cropped_img.save(out_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
    print(f"Successfully cropped and saved to {out_path}")

analyze_and_crop("Source_Code/trade_manager_logo_v4.png", "Source_Code/icon.ico")
