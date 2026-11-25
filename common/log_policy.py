"""Policy for keeping logs diagnostic instead of recording every UI/browser action."""

import re


CRITICAL_TERMS = (
    "错误", "失败", "异常", "超时", "未找到", "警告", "终止", "取消",
    "任务执行完成", "总任务数", "完成任务数", "失败任务数", "失败原因",
)

NOISY_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"已点击", r"正在点击", r"点击['‘]", r"点击 \d+px",
    r"已输入", r"输入完成", r"正在输入", r"查找结果",
    r"正在查找", r"找到.*元素", r"当前页面标题", r"当前URL",
    r"标题文本", r"页面链接", r"链接文本", r"等待上传完成",
    r"第 \d+ 次检查", r"准备上传", r"已设置文件路径",
    r"图片上传成功", r"文件上传成功", r"图片已成功加载", r"处理成功",
    r"任务 \d+ 成功", r"值 .*处理成功", r"正在处理第",
    r"开始处理第", r"正在访问目标页面", r"页面跳转完成",
    r"检测到输入框", r"重置线程", r"准备登录.*用户名",
    r"tbody的id", r"提取到的tabindex", r"生成的新URL",
    r"字段单元格", r"模拟触发", r"打开配置文件", r"容器HTML",
))


def is_diagnostic_message(message):
    text = str(message)
    if text.startswith(('[HTTP]', '[执行明细]', '[逐行结果]')):
        return True
    if any(term in text for term in CRITICAL_TERMS):
        return True
    return not any(pattern.search(text) for pattern in NOISY_PATTERNS)


class DiagnosticLogFilter:
    def filter(self, record):
        return is_diagnostic_message(record.getMessage())
