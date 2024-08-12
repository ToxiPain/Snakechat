git clone --depth 1 https://github.com/tulir/whatsmeow.git
rm -rf gosnakechat/defproto
mv whatsmeow/proto gosnakechat/defproto
rm gosnakechat/defproto/*/*.pb.*
rm gosnakechat/defproto/*/*.go
rm gosnakechat/defproto/.gitignore
rm gosnakechat/defproto/*.*
rm -rf whatsmeow
cp gosnakechat/snakechat.proto gosnakechat/defproto
