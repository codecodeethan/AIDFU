import qrcode

# Replace this with your GitHub Pages URL
url = "https://github.com/codecodeethan/AIDFU.git"

# Generate QR code
qr = qrcode.make(url)

# Save QR code image
qr.save("qr_code.png")