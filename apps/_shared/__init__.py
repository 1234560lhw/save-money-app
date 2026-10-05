"""共享 UI 层：主题、应用外壳、页面组件。

桌面端（apps/desktop）与手机端（apps/mobile）引用的是**同一份**界面代码，
只有窗口尺寸、标题、以及个别平台能力（文件选择器）不同。
"""

from __future__ import annotations

__all__ = ["theme", "shell", "views", "components"]
