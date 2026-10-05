# 静态资源目录

打包时 `flet build` 会把这里的内容一起打进去。

## 需要的文件

| 文件 | 用途 | 规格建议 |
| --- | --- | --- |
| `icon.png` | 桌面端窗口图标 / 手机 App 图标 | 512×512 或 1024×1024 的 PNG，透明背景 |
| `splash_android.png` | Android 启动图（可选） | 竖版，深色背景上不刺眼 |

目前**没有放图片**：仓库里不放二进制资源，图标请自行放入本目录后即可生效
（命令里已通过 `assets_dir="assets"` 指向这里）。

## 自己做一个临时图标

没有设计资源时，可以先用纯色方块占位：

```powershell
.venv\Scripts\python.exe -c "from PIL import Image; Image.new('RGBA',(1024,1024),(0,137,123,255)).save('assets/icon.png')"
```

（需要 Pillow，按需安装：`scripts\install_deps.py pillow`）
