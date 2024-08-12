protoc --go_out=. snakechat.proto def.proto && protoc --python_out=../proto --mypy_out=../proto def.proto snakechat.proto
python3 build.py
protoc --go_out=. --go-grpc_out=. -I . snakechat.proto def.proto 
if [[ -f defproto ]]
then
rm -rf defproto
fi
mv -f github.com/ToxiPain/snakechat/defproto/* defproto
rm -rf github.com/
GOOS=linux GOARCH=amd64 CGO_ENABLED=1 go build -buildmode=c-shared -ldflags=-s -o snakechat.so main.go
mv snakechat.so ..


