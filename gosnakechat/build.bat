:: Set environment variables
set GOOS=windows
set GOARCH=amd64
set CGO_ENABLED=1
set CC=x86_64-w64-mingw32-gcc

:: Generate Go code using protoc
protoc --go_out=. snakechat.proto def.proto
protoc --python_out=../proto --mypy_out=../proto def.proto snakechat.proto

:: Run Python build script
python build.py

:: Generate Go code for gRPC
protoc --go_out=. --go-grpc_out=. -I . snakechat.proto def.proto

:: Clean up and move generated files
if exist defproto rmdir /s /q defproto
if exist github.com/ToxiPain/snakechat/defproto move github.com/ToxiPain/snakechat/defproto defproto
rmdir /s /q github.com

:: Build the Go shared library
go build -buildmode=c-shared -ldflags=-s -o snakechat.dll main.go
move /Y snakechat.dll ..
