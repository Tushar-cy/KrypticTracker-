#!/bin/bash
# Setup script for KrypticTrack extensions

echo "🚀 Setting up KrypticTrack Extensions..."

# VS Code Extension
echo ""
echo "📝 Setting up VS Code Extension..."
cd vscode
if [ ! -d "node_modules" ]; then
    echo "Installing VS Code extension dependencies..."
    npm install
else
    echo "Dependencies already installed"
fi

echo "Compiling TypeScript..."
npm run compile

if [ $? -eq 0 ]; then
    echo "✅ VS Code extension ready!"
else
    echo "❌ VS Code extension compilation failed"
fi

cd ..

# Chrome Extension
echo ""
echo "🌐 Setting up Chrome Extension..."

# Create placeholder icons if they don't exist
if [ ! -f "chrome/icons/icon16.png" ]; then
    echo "Creating placeholder icons..."
    # Try to create simple icons using ImageMagick or Python
    if command -v convert &> /dev/null; then
        convert -size 16x16 xc:#4ec9b0 chrome/icons/icon16.png
        convert -size 48x48 xc:#4ec9b0 chrome/icons/icon48.png
        convert -size 128x128 xc:#4ec9b0 chrome/icons/icon128.png
        echo "✅ Icons created with ImageMagick"
    elif command -v python3 &> /dev/null; then
        python3 << 'EOF'
from PIL import Image
colors = {
    16: (78, 201, 176),  # #4ec9b0
    48: (78, 201, 176),
    128: (78, 201, 176)
}
for size in [16, 48, 128]:
    img = Image.new('RGB', (size, size), colors[size])
    img.save(f'chrome/icons/icon{size}.png')
print("✅ Icons created with PIL")
EOF
        if [ $? -eq 0 ]; then
            echo "✅ Icons created with Python PIL"
        else
            echo "⚠️  Could not create icons automatically"
            echo "   Please create icon16.png, icon48.png, icon128.png manually"
        fi
    else
        echo "⚠️  ImageMagick or PIL not found"
        echo "   Please create icon files manually or install:"
        echo "   - ImageMagick: sudo apt-get install imagemagick"
        echo "   - Or Python PIL: pip install Pillow"
    fi
else
    echo "✅ Icons already exist"
fi

echo ""
echo "🎉 Extension setup complete!"
echo ""
echo "Next steps:"
echo "1. VS Code: Press F5 in VS Code to test the extension"
echo "2. Chrome: Load chrome/ directory as unpacked extension"
echo "3. Make sure Flask backend is running on http://localhost:5000"



