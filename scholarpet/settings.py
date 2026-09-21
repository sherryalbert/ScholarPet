from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QFormLayout, QComboBox, QLineEdit, QSpinBox, QCheckBox,
    QPlainTextEdit, QColorDialog, QMessageBox)
from .views import STYLE
from .config import save_settings


class SettingsDialog(QDialog):
    saved = Signal(dict)

    def __init__(self, settings):
        super().__init__()
        self.values = dict(settings)
        self.setWindowTitle("研译 · 外观与翻译设置"); self.resize(660, 590)
        self.setObjectName("surface"); self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self); layout.setContentsMargins(25, 22, 25, 22); layout.setSpacing(15)
        title = QLabel("让研译更合你的习惯"); title.setObjectName("title"); layout.addWidget(title)
        tabs = QTabWidget(); layout.addWidget(tabs)
        appearance = QWidget(); form = QFormLayout(appearance); form.setSpacing(20)
        self.color = settings["color"]
        colors = QHBoxLayout()
        for name, value in [("鸢尾紫", "#6475ed"), ("青瓷绿", "#35a99a"), ("樱花粉", "#db86a5"), ("琥珀橙", "#d99a4c"), ("星空蓝", "#438dbd")]:
            button = QPushButton(name); button.setStyleSheet(f"background:{value};color:white;padding:8px;border:0")
            button.clicked.connect(lambda checked=False, c=value: self.pick_color(c)); colors.addWidget(button)
        form.addRow("桌宠皮肤", colors)
        self.color_btn = QPushButton(self.color); self.color_btn.clicked.connect(self.custom_color); form.addRow("自定义颜色", self.color_btn)
        self.size_spin = QSpinBox(); self.size_spin.setRange(76, 160); self.size_spin.setValue(settings["pet_size"]); self.size_spin.setSuffix(" 像素"); form.addRow("桌宠大小", self.size_spin)
        self.opacity = QSpinBox(); self.opacity.setRange(45, 100); self.opacity.setValue(settings["opacity"]); self.opacity.setSuffix(" %"); form.addRow("桌宠不透明度", self.opacity)
        self.animate = QCheckBox("活灵活现：眨眼、动嘴、眼睛跟随鼠标、轻轻浮动")
        self.animate.setChecked(settings["animate"]); form.addRow("动画", self.animate)
        self.avatar = QCheckBox("使用灰原哀 Q 版头像（关闭则用可换色的矢量桌宠）")
        self.avatar.setChecked(settings.get("pet_avatar", True)); form.addRow("桌宠形象", self.avatar)
        self.topmost = QCheckBox("始终显示在其它窗口之上（浏览器全屏时也不消失）")
        self.topmost.setChecked(settings.get("topmost", True)); form.addRow("窗口层级", self.topmost)
        self.view = QComboBox(); self.view.addItem("原位中文覆盖", "overlay"); self.view.addItem("中英对照阅读窗", "reader")
        self.view.setCurrentIndex(max(0, self.view.findData(settings["view"]))); form.addRow("整屏翻译后展示", self.view)
        self.font_size = QSpinBox(); self.font_size.setRange(12, 24); self.font_size.setValue(settings["font_size"]); self.font_size.setSuffix(" 像素"); form.addRow("译文字号", self.font_size)
        tabs.addTab(appearance, "外观")
        selection = QWidget(); sform = QFormLayout(selection); sform.setSpacing(16)
        self.selection_on = QCheckBox("开启：选中英文后自动在鼠标旁弹出中文")
        self.selection_on.setChecked(settings.get("selection_enabled", True)); sform.addRow("划词翻译", self.selection_on)
        self.popup_side = QComboBox(); self.popup_side.addItem("自动（优先鼠标右侧）", "auto")
        self.popup_side.addItem("固定在鼠标右侧", "right"); self.popup_side.addItem("固定在鼠标左侧", "left")
        self.popup_side.setCurrentIndex(max(0, self.popup_side.findData(settings.get("popup_side", "auto"))))
        sform.addRow("翻译浮窗位置", self.popup_side)
        self.popup_width = QSpinBox(); self.popup_width.setRange(320, 720); self.popup_width.setValue(int(settings.get("popup_width", 430)))
        self.popup_width.setSuffix(" 像素"); sform.addRow("翻译浮窗宽度", self.popup_width)
        sform.addRow(QLabel(""))
        howto = QLabel("划词翻译在后台读取当前应用的文字选区（向前台应用发一次复制指令，读完就把你的剪贴板原样放回；"
                       "不会清空剪贴板，刚截的图仍然可以直接粘贴；也不记录键盘）。"
                       "双击一个英文单词、或按住拖动划过一段文字即可触发，浮窗不遮挡选中内容、也不会抢走输入焦点。"
                       "终端、密码框和凭据窗口会被自动跳过。扫描版 PDF 没有文字层，浮窗会提示改用「框选翻译」。")
        howto.setWordWrap(True); howto.setObjectName("muted"); sform.addRow(howto)
        tabs.addTab(selection, "划词翻译")
        engines = QWidget(); eform = QFormLayout(engines); eform.setSpacing(15)
        self.engine = QComboBox(); self.engine.addItem("本地离线 · Argos 英中模型（推荐）", "offline"); self.engine.addItem("Google 免费翻译（非官方接口，实验性）", "google"); self.engine.addItem("学术增强 · DeepSeek / 兼容 API", "llm")
        self.engine.setCurrentIndex(max(0, self.engine.findData(settings["engine"]))); eform.addRow("翻译引擎", self.engine)
        notice = QLabel("本地模式无需网络或密钥，模型已随项目提供，适合 IEEE 页面和常见通信术语。Google 模式无需密钥但可能限流。学术增强模式按上下文和术语表翻译，需要你自己的 API 密钥，费用由服务商收取。三种模式均可能误译，关键结论请核对原文。")
        notice.setWordWrap(True); notice.setObjectName("muted"); eform.addRow(notice)
        self.base = QLineEdit(settings["api_base"]); eform.addRow("API Base URL", self.base)
        self.model = QLineEdit(settings["api_model"]); eform.addRow("模型名称", self.model)
        self.key = QLineEdit(settings["api_key"]); self.key.setEchoMode(QLineEdit.EchoMode.Password); self.key.setPlaceholderText("输入服务商 API Key；本地模型可留空")
        eform.addRow("API 密钥", self.key)
        privacy = QLabel("截图与 OCR 在本机处理，仅识别出的文字发送到所选翻译服务；不自动保存截图、译文或历史。密钥用 Windows DPAPI 加密保存在本机，不进入 GitHub。涉密或未公开材料可使用本地兼容接口。")
        privacy.setWordWrap(True); privacy.setObjectName("muted"); eform.addRow(privacy)
        self.engine.currentIndexChanged.connect(self.engine_changed); self.engine_changed()
        tabs.addTab(engines, "翻译与隐私")
        terms = QWidget(); tform = QVBoxLayout(terms)
        hint = QLabel("已内置通信与抗干扰常用术语。下面可追加或覆盖，每行格式：英文 = 中文。")
        hint.setWordWrap(True); tform.addWidget(hint)
        self.glossary = QPlainTextEdit(); self.glossary.setPlaceholderText("beamforming = 波束成形\njamming = 人为干扰\nspread spectrum = 扩频")
        self.glossary.setPlainText('\n'.join(f'{k} = {v}' for k,v in settings.get('glossary',{}).items())); tform.addWidget(self.glossary)
        tabs.addTab(terms, "专业术语")
        about = QWidget(); al = QVBoxLayout(about)
        info = QLabel("研译 ScholarPet 0.5.0 · 灰原哀版\n\n【主要用法】在论文、网页、技术报告里划选英文，鼠标旁立刻弹出中文，不遮挡选中内容，也不抢焦点。双击单词或拖动划句都会触发。\n\n记四个动作就够了，研译不注册任何全局快捷键：\n· 鼠标划选：选中哪里就翻译哪里\n· 单击灰原哀头像：整屏翻译\n· 点击头像下方「框选翻译」：拖动框选做 OCR，扫描版 PDF 用这个\n· 双击头像：打开此设置\n拖动头像：移动位置；右键头像：更多功能（含「翻译剪贴板文字」）\n在浮窗以外的任何地方单击左键：浮窗立刻收起；浮窗上的「复制中文」「完整对照」照常可用\nEsc：关闭浮窗 / 覆盖层 / 取消框选\n\n【桌宠动作】她会自己眨眼（偶尔连眨两下）、视线跟着鼠标走，你点击她时也会眨一下回应；翻译进行中会轻轻动嘴。所有动作都是小幅度的，不抢注意力。不想要可在「外观」里取消勾选「活灵活现」。\n\n【窗口层级】默认勾选「始终显示在其它窗口之上」，浏览器按 F11 全屏或阅读器全屏时，桌宠和翻译浮窗依然可见；取消勾选则只在普通桌面窗口之上。\n\n翻译对象是屏幕当前可见内容。滚动、翻页后再翻译一次。\n首轮 OCR 初始化稍慢；受保护视频或安全桌面可能无法截图。\n扫描版 PDF 没有文字层，请改用「框选翻译」。")
        info.setWordWrap(True); al.addWidget(info); al.addStretch(); tabs.addTab(about, "使用说明")
        row = QHBoxLayout(); row.addStretch()
        cancel = QPushButton("取消"); cancel.clicked.connect(self.reject); row.addWidget(cancel)
        save = QPushButton("保存设置"); save.setObjectName("primary"); save.clicked.connect(self.save); row.addWidget(save); layout.addLayout(row)

    def engine_changed(self):
        for widget in [self.base, self.model, self.key]:
            widget.setEnabled(self.engine.currentData() == 'llm')

    def pick_color(self, color):
        self.color = color; self.color_btn.setText(color); self.color_btn.setStyleSheet(f'color:{color}')

    def custom_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "选择桌宠颜色")
        if color.isValid():
            self.pick_color(color.name())

    def save(self):
        glossary = {}
        for line in self.glossary.toPlainText().splitlines():
            if not line.strip(): continue
            if '=' not in line:
                QMessageBox.warning(self, "术语格式", "请使用 英文 = 中文 格式，每行一个术语。"); return
            key, value = line.split('=', 1)
            if not key.strip() or not value.strip():
                QMessageBox.warning(self, "术语格式", "英文和中文都不能为空。"); return
            glossary[key.strip()] = value.strip()
        self.values.update(color=self.color, pet_size=self.size_spin.value(), opacity=self.opacity.value(),
                           animate=self.animate.isChecked(), pet_avatar=self.avatar.isChecked(),
                           topmost=self.topmost.isChecked(),
                           view=self.view.currentData(), font_size=self.font_size.value(),
                           selection_enabled=self.selection_on.isChecked(), popup_side=self.popup_side.currentData(),
                           popup_width=self.popup_width.value(),
                           engine=self.engine.currentData(), api_base=self.base.text().strip(),
                           api_model=self.model.text().strip(), api_key=self.key.text().strip(), glossary=glossary)
        try:
            save_settings(self.values)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc)); return
        self.saved.emit(self.values); self.accept()
