# NTU 空调免费使用 / AC-FREE ESP32 红外维持控制器

这是一个基于 **ESP32-WROOM-32 + MicroPython** 的空调红外维持控制器项目，不涉及任何对NTU宿舍空调的物理与电路的修改和不可逆破坏。

本项目不是普通万能空调遥控器。目标空调经常出现app充值功能异常，在无余额情况下需要持续收到完整空调状态红外帧才能保持临时运行（是的，你不需要app有余额）。ESP32 会根据外置 DHT11 温度传感器进行窗口温控，并在需要制冷时以固定 **0.8 秒间隔**持续发送已学习的红外指令。

项目源码公开，但禁止商业使用。详见 `LICENSE`。

## 当前功能

- ESP32-WROOM-32 运行 MicroPython 固件。
- 使用 IRO5T UART 红外学习/发射模块。
- 使用 DHT11 读取室温和湿度。
- 使用 0.96 寸 SPI OLED 显示本地状态。
- 使用 3 个实体按键进行本地菜单操作。
- 使用 Blinker BLE 手机端控制。
- Wi-Fi 仅用于配网和 NTP 校时，不依赖服务器。
- 网页只保留极简 Wi-Fi 配置和时间状态显示。
- 不使用 MQTT / Home Assistant。

## 硬件清单

| 元件 | 型号 / 说明 | 数量 |
| --- | --- | ---: |
| 主控 | ESP32-WROOM-32 开发板 | 1 |
| 红外模块 | IRO5T UART 红外学习/发射模块 | 1 |
| 屏幕 | 0.96 寸 SPI OLED，SSD1306/SH1106 兼容 | 1 |
| 温湿度传感器 | DHT11 | 1 |
| 按键 | 普通轻触按键，低电平触发 | 3 |
| 电源 | USB 5V 稳定供电 | 1 |
| 杜邦线 / 面包板 / 焊接材料 | 按实际安装方式选择 | 若干 |

## 接线表

| 功能 | ESP32 GPIO | 说明 |
| --- | ---: | --- |
| IRO5T TX | GPIO23 | ESP32 UART RX 侧使用 |
| IRO5T RX | GPIO22 | ESP32 UART TX 侧使用 |
| IRO5T Baudrate | 9600 | 固定串口波特率 |
| OLED SCK | GPIO5 | SPI 时钟 |
| OLED MOSI | GPIO18 | SPI 数据 |
| OLED RES | GPIO19 | Reset |
| OLED DC | GPIO21 | Data / Command |
| OLED CS | GND | CS 直接接地 |
| DHT11 DATA | GPIO17 | 温湿度数据 |
| B1 | GPIO15 | 本地菜单返回 / 页面切换 |
| B2 | GPIO4 | 确认 / 执行当前项 |
| B3 | GPIO16 | 下一项 / 调整数值 |

所有模块必须共地。

## 串口驱动与电脑连接

ESP32-WROOM-32 开发板本身通常通过 USB 转串口芯片连接电脑。不同开发板可能使用不同芯片：

- CP210x：常见于 ESP32 DevKitC 类开发板。
- CH340 / CH341：常见于廉价 ESP32 开发板。
- FTDI：部分开发板或外接下载器使用。

更方便的方法是向商家索要驱动文件

如果 Windows 设备管理器里看不到 COM 口，先确认 USB 线不是“只能充电”的线，再安装对应驱动。

推荐官方/厂家链接：

- Espressif 串口连接说明：  
  https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/establish-serial-connection.html
- CP210x 驱动：  
  https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers
- CH340 / CH341 驱动：  
  https://www.wch.cn/downloads/CH341SER_EXE.html
- FTDI VCP 驱动：  
  https://ftdichip.com/drivers/vcp-drivers/

Windows 检查方法：

1. 插上 ESP32。
2. 打开“设备管理器”。
3. 查看“端口 COM 和 LPT”。
4. 拔掉 ESP32 再插回，观察新增或消失的 COM 口。
5. 在 Thonny 中选择该 COM 口。

## MicroPython 环境配置

推荐使用 Thonny 上传和调试 MicroPython 文件。

参考链接：

- MicroPython ESP32 官方教程：  
  https://docs.micropython.org/en/latest/esp32/tutorial/intro.html
- MicroPython ESP32 固件下载：  
  https://micropython.org/download/ESP32_GENERIC/
- Thonny 下载：  
  https://thonny.org/

基本流程：

1. 安装 Thonny。
2. 使用 USB 连接 ESP32。
3. 在 Thonny 中打开：
   `工具 -> 选项 -> 解释器`
4. 选择：
   `MicroPython (ESP32)`
5. 选择正确 COM 口。
6. 如未刷入 MicroPython，使用 Thonny 的安装/刷写功能刷入 ESP32 MicroPython 固件。
7. 上传本项目文件到 ESP32 文件系统。

## 需要上传到 ESP32 的文件

上传到 ESP32 根目录：

```text
/main.py
/src
/ir_profiles
/ir_codes
/ssd1306.py
```
请根据实际的oled显示器类型选择适合的驱动程序，ssd1306.py目前只适配0.96英寸的7针oled模块



## AC-FREE 工作逻辑

本项目的核心逻辑是：

- `strong_001.bin` 是当前已知可靠的强劲/开机维持指令。
- 风量 1 到 5 需要用户通过 IRO5T 本地学习得到。
- 每个风量文件都应是完整空调状态指令：
  - 制冷模式
  - 18 摄氏度
  - 指定风量
- 当温控判断需要制冷时，ESP32 必须每 0.8 秒发送一次当前风量对应的红外指令。
- 如果当前风量指令不存在，则 fallback 到 `strong_001.bin`。
- AC-FREE 关闭时不发送红外，让空调自然停止。

风量定义：

| 风量值 | 文件 / 命令 |
| ---: | --- |
| 1 | `fan_1` |
| 2 | `fan_2` |
| 3 | `fan_3` |
| 4 | `fan_4` |
| 5 | `fan_5` |
| 6 | `strong` |

## 温控逻辑

温控由 ESP32 和 DHT11 完成，不依赖空调自带温控。

默认逻辑：

- 目标温度最低为 18 摄氏度。
- 当前温度高于 `target + 0.5C` 时开始制冷。
- 当前温度低于 `target - 1.0C` 时停止发送红外。
- 如果检测到温度快速下降，认为传感器可能被冷风直吹，停止窗口可放宽到 `target - 2.0C`。
- DHT11 数据会做滚动平均，避免单次跳变导致频繁启停。

## OLED 与实体按键

OLED 显示英文状态信息。

按键逻辑：

- 暗屏时，任意按键第一次只点亮屏幕，不执行动作。
- 屏幕 50 秒无操作后自动熄灭。
- B1：返回 / 页面切换。
- B2：确认 / 执行当前项。
- B3：下一项 / 数值增加。
- 长按 B3：上一项 / 数值减少。

本地菜单包括：

- Status
- AC-FREE On / Off
- Set Temp
- Set Fan
- IR Learn
- WiFi Setup

## Blinker  手机端控制

当前固件使用的是 **Blinker BLE 协议兼容接口**。如果你使用的是已适配本项目的 Blinker 手机端界面，请导入额外提供的 App 操作界面代码后使用。
```
/blinder.txt
```
BLE 设备信息：

```text
BLE name: Blinker
Service UUID: 0xFFE0
Characteristic UUID: 0xFFE1
```

组件接口如下：

| 组件类型 | 组件名 | 用途 |
| --- | --- | --- |
| 开关按钮 | `btn-0fh` | AC-FREE 开关 |
| 普通按钮 | `btn-1hh` | 点亮 OLED 屏幕 |
| 普通按钮 | `btn-7j2` | 打开 OLED 状态显示页 |
| 滑块 | `ran-5hc` | 风量选择，1-6 |
| 滑块 | `ran-egl` | 目标温度 |
| 数字显示 | `num-d2v` | 当前温度 |
| 数字显示 | `num-m74` | 当前湿度 |
| 文本显示 | `tex-status` | 当前状态 |

Blinker/BLE 数据格式：

```json
{"btn-0fh":"on"}
{"btn-0fh":"off"}
{"btn-1hh":"tap"}
{"btn-7j2":"tap"}
{"ran-5hc":4}
{"ran-egl":25}
{"get":"state"}
{"rt":["num-d2v","num-m74","ran-5hc","ran-egl"]}
```

ESP32 回传格式示例：

```json
{"btn-0fh":{"switch":"on"}}
{"ran-5hc":{"value":4}}
{"ran-egl":{"value":25}}
{"num-d2v":{"value":28.0}}
{"num-m74":{"value":77}}
{"tex-status":{"text":"AC-FREE fan_4"}}
```

注意：

- 手机端滑块风量范围是 1 到 6。
- 1-5 对应 `fan_1` 到 `fan_5`。
- 6 对应 `strong`。
- IR 学习只允许通过本地 OLED + 实体按键执行，不通过 BLE 执行。

## Wi-Fi 与网页

Wi-Fi 不是必须功能。项目可在未配网情况下本地运行。

Wi-Fi 只用于：

- NTP 获取时间。
- 显示正确时间。
- 首次配置 Wi-Fi。

未配置 Wi-Fi 或连接失败时，ESP32 会启动 AP：

```text
SSID: AC-SETUP
Password: yzc202657
Address: 192.168.4.1
```

网页只用于：

- 保存 Wi-Fi SSID / 密码。
- 跳过 Wi-Fi。
- 查看时间和基础状态。

网页不是空调遥控器。

## 红外学习

红外学习通过本地 OLED 菜单完成：

```text
IR Learn
Fan 1
Fan 2
Fan 3
Fan 4
Fan 5
Strong
```

学习风量时，请把原装遥控器设置为：

- 制冷模式
- 18 摄氏度
- 对应风量

然后对准 IRO5T 发送一次完整空调状态下的开机指令。

学习失败时不会覆盖旧文件。重新学习同一槽位，成功后才替换旧文件。

## 已知限制

- DHT11 精度低、响应慢，只适合粗略温控。
- 目标空调收到余额检测限制，所以 0.8 秒 IR 发送间隔是硬要求，导致可能的噪音和灯光闪烁。
- 通用大金红外库不一定适配所有 NTU 宿舍空调。
- 学习到的 IRO5T 二进制指令是当前最可靠方案。
- 本项目没有 MQTT / Home Assistant。
- 本项目没有云服务器依赖。
## 解决方法
- 采用医用脱脂棉填充空调蜂鸣器开口处
- 利用大块遮光胶带覆盖运行状态指示灯和蜂鸣器开口
- 为可逆改造，脱脂棉可轻易完整取出

## 许可

本项目源码公开，仅允许个人、学习、研究和非商业用途。

未经作者明确书面许可，禁止商业使用、商业部署、商业销售或作为商业产品的一部分使用。

许可证：

```text
PolyForm Noncommercial License 1.0.0
```

## 打赏支持

如果这个项目帮到了你，可以自愿打赏支持作者继续维护。

打赏不代表获得商业授权。本项目仍然仅允许个人、学习、研究和非商业用途；商业使用需要获得作者明确书面许可。

### 微信支付

![微信支付收款码](assets/donate/wechat.jpg)

### 支付宝

![支付宝收款码](assets/donate/alipay.jpg)
### paypal

![paypal收款码](assets/donate/paypal.jpg)
