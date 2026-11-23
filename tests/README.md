# 核心流程验证

在 Linux 开发机上运行：

```bash
cd /workspace/classroom-lab
./start_verify.sh
```

或：

```bash
.venv/bin/python tests/test_flow.py
```

测试会启动教师机服务端和 3 个模拟学生端，依次验证：

1. 教师登录（错误密码被拒绝）
2. 带加入码的学生自动批准，未带码的进入待批准，教师点允许加入
3. 开始上课后收到 3 台缩略图
4. 单人查看
5. 锁屏 / 解锁指令到达学生端
6. 公告到达
7. 文件到达并保存
8. 广播测试图到达
9. 下课后学生端停止传屏，服务端丢弃屏幕缓存
10. 设置默认桌面并锁定；下课与学生端重启后仍保持；老师解除后恢复

测试不涉及键盘记录、剪贴板或隐藏进程。


另请运行：

```bash
.venv/bin/python tests/test_web_filter.py
```

验证网页游戏/下载拦截、白名单、教师机下发 .cpp、下课后限制关闭。

另请运行：

```bash
.venv/bin/python tests/test_desktop.py
```

验证默认桌面的设置、锁定、被改后恢复、模拟重启后重新应用，以及解除锁定后恢复原壁纸（Linux 为模拟实现，不调用 Windows API）。`./start_verify.sh` 已包含此项。完整流程里还会检查：下发到三台学生机、下课不解除锁定、重启学生端后仍锁定、老师解除后恢复。

另请运行 `tests/test_win7_deps.py`（`./start_verify.sh` 已包含）：确认 Windows 安装依赖不包含 `pydantic-core`，以及教师/学生启动器失败时会写出可发给开发者的日志。

另请运行 `tests/test_win_types.py`（`./start_verify.sh` 已包含）：
在 Linux 上用仿 CPython 3.8.10 的 `ctypes.wintypes`（没有 `HCURSOR`）验证兼容补丁；
确认 `import teacher.win_console` / `student.win_config` / `student.win_ui` 不会因
缺少 `HCURSOR` 而崩溃，且 `WNDCLASSW` 能定义。不启动真实 Win32 窗口。

另请运行 `tests/test_teacher_client.py`（`./start_verify.sh` 已包含）：
在 Linux 上启动教师机服务，用原生窗口使用的 API 客户端验证登录、上课、换码、公告、发文件、
限制名单、广播与默认桌面等接口，以及状态文案映射。不启动 Win32 窗口。

另请运行 `tests/test_credentials.py`（`./start_verify.sh` 已包含）：
在 Linux 上用可注入的假存储验证记住密码的保存、预填、取消勾选清除、登录失败不保存、改密后更新；
登录 401 显示「账号或密码不正确」而不是「登录已过期」；以及在临时 data 目录重置为默认密码后可登录。
不打开 Win32 窗口，测试输出不含明文密码。
