#!/usr/bin/env python3
"""Create placeholder icons for Chrome extension."""

try:
    from PIL import Image
    
    # Create icons
    sizes = [16, 48, 128]
    color = (78, 201, 176)  # #4ec9b0 (teal color)
    
    for size in sizes:
        img = Image.new('RGB', (size, size), color)
        img.save(f'icons/icon{size}.png')
        print(f"✅ Created icon{size}.png")
    
    print("\n🎉 All icons created successfully!")
    
except ImportError:
    print("❌ PIL (Pillow) not installed")
    print("Install it with: pip install Pillow")
    print("\nOr create icons manually:")
    print("- icon16.png (16x16)")
    print("- icon48.png (48x48)")
    print("- icon128.png (128x128)")
    exit(1)



