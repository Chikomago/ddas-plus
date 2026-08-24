"""PIM browser automation business logic. No TTK widgets or UI variables live here."""

import logging
import os
import time
import threading
import openpyxl
from common.browser import create_browser, close_browser
from common.settings import Settings as AppSettings
from common.task_models import PimTaskRequest, TaskCallbacks, TaskResult
from common.task_results import TaskReport, format_task_report


class PimTask:
    """PIM task entry containing element lookup, click, input and upload workflow."""

    def __init__(self, request: PimTaskRequest, callbacks: TaskCallbacks, stop_event=None):
        self.request = request
        self.callbacks = callbacks
        self.stop_flag = stop_event or threading.Event()
        self.page = None

    def confirm(self, message):
        return self.callbacks.confirm(message) if self.callbacks.confirm else True

    def notify_error(self, message):
        self.callbacks.error(message)

    def notify_warning(self, message):
        (self.callbacks.warning or self.callbacks.log)(message)

    def notify_info(self, message):
        (self.callbacks.info or self.callbacks.log)(message)

    def load_settings(self):
        settings = AppSettings()
        settings.load_settings()
        return {
            "browser_path": settings.settings.get("chrome_path", ""),
            "pixel_size": settings.settings.get("pim_settings", {}).get("pixel_size", "750"),
        }

    def close_page(self, keep_open=False):
        self.page = close_browser(self.page, keep_open=keep_open, log=logging.info)

    def run(self):
        self.callbacks.status("正在执行")
        try:
            self.run_task_logic(self.request)
            if self.stop_flag.is_set():
                self.callbacks.status("已终止")
                return TaskResult(False, "任务已终止", {"cancelled": True})
            self.callbacks.status("已完成")
            return TaskResult(True, "任务完成")
        except Exception as error:
            self.callbacks.error(str(error))
            self.callbacks.status("执行失败")
            return TaskResult(False, str(error))
        finally:
            if self.callbacks.finished:
                self.callbacks.finished()

    def request_stop(self):
        """响应公共任务管理器的终止请求并释放浏览器。"""
        self.stop_flag.set()
        self.callbacks.status("正在终止...")
        self.close_page()

    def initialize_chrome_driver(self):
        logging.info("初始化 DrissionPage...")
        try:
            # 加载设置
            try:
                settings = self.load_settings()
            except Exception as error:
                settings = {}
                logging.info(f"读取统一设置失败，使用默认配置: {error}")

            browser_path = settings.get('browser_path')
            if browser_path and os.path.exists(browser_path):
                logging.info(f"使用自定义浏览器路径: {browser_path}")
            else:
                logging.info("使用默认浏览器配置")
                browser_path = None

            self.page = create_browser(browser_path, mute=True, load_timeout=30)
            logging.info("DrissionPage 初始化成功")
            return True
        except Exception as e:
            logging.info(f"DrissionPage 初始化失败: {e}")
            self.notify_error(f"未能初始化 DrissionPage: {e}\n请检查浏览器设置")
            return False

    def run_task_logic(self, request):
        logging.info("开始处理...")

        # 检查是否勾选了"配置预设模块"
        if request.preset_module:

            if not self.initialize_chrome_driver():
                return

            try:
                # 首先打开登录页面
                self.page.get("https://pim.leycloud.com/")
                logging.info("已打开页面: https://pim.leycloud.com/")

                # 检查当前URL是否已经是home页面（已登录状态）
                current_url = self.page.url
                if "https://pim.leycloud.com/home" in current_url:
                    logging.info("检测到已经登录，直接进入下一步")
                else:
                    logging.info("需要登录，等待用户操作...")
                    #
                    # 使用循环检查URL变化
                    logging.info("等待登录完成...")
                    start_time = time.time()
                    while time.time() - start_time < 60:  # 最多等待60秒
                        if "https://pim.leycloud.com/home" in self.page.url:
                            logging.info("检测到登录成功")
                            break
                        time.sleep(1)  # 每秒检查一次
                    else:
                        logging.info("登录超时，请手动确认")

                # 提示用户手动进入预设模块页面
                logging.info("等待用户进入预设模块页面URL...")

                # 等待用户进入预设模块页面URL
                found = False
                timeout = 300  # 设置5分钟超时
                start_time = time.time()

                while time.time() - start_time < timeout and not found and not self.stop_flag.is_set():
                    try:
                        # 检查当前URL是否是预设模块页面
                        current_url = self.page.url
                        if "https://pim.leycloud.com/product/setting/detail-page/preset" in current_url:
                            found = True
                            logging.info("检测到预设模块页面URL")

                            # 询问用户是否执行任务
                            if self.confirm("已检测到预设模块页面，请确保当前选择模块正确，是否继续执行'新建'名称流程？"):
                                logging.info("选择继续执行任务，将执行'新建'名称流程")

                                selected_px = request.pixel_size or "750"
                                logging.info(f"选择 {selected_px}px")

                                # 使用从配置文件读取的像素大小
                                selected_px = selected_px  # 已经在上面的代码中设置
                                logging.info(f"使用像素大小: {selected_px}px")

                                try:
                                    # 点击"新建"按钮
                                    new_button = self.page.ele('xpath://button[@class="pmdm-btn pmdm-btn-primary"]/span[text()="新 建"]/..')
                                    if new_button:
                                        new_button.click()

                                        # 在页面上点击相应的单选按钮
                                        time.sleep(0.2)  # 等待单选按钮出现
                                        try:
                                            # 直接查找并点击带有特定值的单选按钮
                                            radio_selector = f'css:input[type="radio"].pmdm-radio-input[value="{selected_px}"]'
                                            radio_button = self.page.ele(radio_selector)
                                            if radio_button:
                                                radio_button.click()
                                            else:
                                                logging.info(f"错误：未能找到 {selected_px}px 按钮")
                                        except Exception as e:
                                            logging.info(f"尺寸选择失败: {e}")

                                        # 读取配置文件中A列第2行开始的所有值
                                        try:
                                            if not request.config_path:
                                                self.notify_error("请先生成或选择配置文件")
                                                logging.info("错误: 未选择配置文件")
                                                return

                                            wb = openpyxl.load_workbook(request.config_path)
                                            ws = wb.active
                                            total_rows = ws.max_row - 1
                                            values_to_input = []

                                            for row in range(2, ws.max_row + 1):
                                                value = ws.cell(row=row, column=1).value
                                                if value:  # 确保值不为空
                                                    values_to_input.append(value)

                                            logging.info(f"从配置文件中读取了 {len(values_to_input)} 个值")

                                            # 初始化统计变量
                                            success_count = 0
                                            fail_count = 0
                                            fail_reasons = []
                                            start_time = time.time()

                                            # 处理每个值
                                            for index, value in enumerate(values_to_input):
                                                if self.stop_flag.is_set():
                                                    logging.info("任务被终止")
                                                    break


                                                try:
                                                    # 等待输入框出现
                                                    input_found = False
                                                    input_timeout = 60  # 设置1分钟超时
                                                    input_start_time = time.time()

                                                    while time.time() - input_start_time < input_timeout and not input_found and not self.stop_flag.is_set():
                                                        try:
                                                            # 尝试查找输入框元素
                                                            input_field = self.page.ele('xpath://input[@placeholder="请输入" and @class="pmdm-input"]', timeout=1)
                                                            if input_field:
                                                                input_found = True

                                                                # 输入值
                                                                try:
                                                                    # 使用DrissionPage库的输入方法
                                                                    input_field.input(value)
                                                                except Exception as e:
                                                                    logging.info(f"输入文本时发生错误: {e}")
                                                                    raise Exception(f"输入文本失败: {e}")
                                                        except Exception as e:
                                                            if "输入文本失败" in str(e):
                                                                raise
                                                            # 元素未找到，继续等待
                                                            time.sleep(2)

                                                    if not input_found:
                                                        raise Exception("等待超时，未检测到输入框")

                                                    # 点击确定按钮
                                                    confirm_button = self.page.ele('xpath://button[@type="button" and @class="pmdm-btn pmdm-btn-primary"]/span[text()="确 定"]/..')
                                                    if confirm_button:
                                                        confirm_button.click()
                                                        time.sleep(0.1)  # 进一步减少等待时间，从0.2秒减少到0.1秒
                                                    else:
                                                        raise Exception("未找到'确定'按钮")

                                                    # 如果还有更多值需要处理，点击新建按钮
                                                    if index < len(values_to_input) - 1:
                                                        time.sleep(1)  # 等待页面刷新
                                                        new_button = self.page.ele('xpath://button[@class="pmdm-btn pmdm-btn-primary"]/span[text()="新 建"]/..')
                                                        if new_button:
                                                            new_button.click()
                                                            time.sleep(0.5)  # 减少等待时间，从1秒减少到0.5秒

                                                            # 在每次点击"新建"按钮后，重新点击单选按钮
                                                            time.sleep(0.2)  # 等待单选按钮出现
                                                            radio_selector = f'css:input[type="radio"].pmdm-radio-input[value="{selected_px}"]'
                                                            radio_button = self.page.ele(radio_selector)
                                                            if radio_button:
                                                                radio_button.click()
                                                            else:
                                                                logging.info(f"警告：未能找到 {selected_px}px 单选按钮")
                                                        else:
                                                            raise Exception("未找到'新建'按钮")

                                                    success_count += 1

                                                except Exception as e:
                                                    fail_count += 1
                                                    fail_reason = f"值 '{value}': {str(e)}"
                                                    fail_reasons.append(fail_reason)
                                                    logging.info(f"处理值 '{value}' 失败: {str(e)}")

                                                    # 如果失败，尝试关闭当前窗口并继续下一个
                                                    try:
                                                        # 尝试查找并点击取消按钮
                                                        cancel_button = self.page.ele('xpath://button[@type="button" and @class="pmdm-btn"]/span[text()="取 消"]/..')
                                                        if cancel_button:
                                                            cancel_button.click()
                                                            time.sleep(1)

                                                        # 如果还有更多值需要处理，点击新建按钮
                                                        if index < len(values_to_input) - 1:
                                                            time.sleep(1)
                                                            new_button = self.page.ele('xpath://button[@class="pmdm-btn pmdm-btn-primary"]/span[text()="新 建"]/..')
                                                            if new_button:
                                                                new_button.click()
                                                                time.sleep(1)

                                                                # 在错误恢复后点击"新建"按钮后，尝试点击单选按钮，但不阻塞流程
                                                                try:
                                                                    # 设置较短的超时时间，避免长时间等待
                                                                    start_time = time.time()
                                                                    max_wait_time = 1  # 最多等待1秒
                                                                    radio_button = None

                                                                    # 尝试查找单选按钮，但设置超时
                                                                    while time.time() - start_time < max_wait_time:
                                                                        radio_selector = f'css:input[type="radio"].pmdm-radio-input[value="{selected_px}"]'
                                                                        radio_button = self.page.ele(radio_selector)
                                                                        if radio_button:
                                                                            break
                                                                        time.sleep(0.1)

                                                                    # 如果找到按钮，则点击
                                                                    if radio_button:
                                                                        radio_button.click()
                                                                    else:
                                                                        logging.info(f"提示：未找到单选按钮或对话框未出现，继续处理")
                                                                except Exception as e:
                                                                    logging.info(f"恢复任务时设置尺寸失败: {e}")
                                                            else:
                                                                logging.info("未找到'新建'按钮，可能无法继续处理")
                                                                break
                                                    except Exception as recovery_error:
                                                        logging.info(f"尝试恢复失败: {recovery_error}")
                                                        break

                                            # 计算总用时
                                            end_time = time.time()
                                            duration = end_time - start_time

                                            report = TaskReport(
                                                len(values_to_input), success_count, fail_count,
                                                duration, failure_details=fail_reasons,
                                            )
                                            result_message = format_task_report(report)
                                            logging.info(result_message)
                                            self.notify_info(result_message)

                                        except Exception as e:
                                            logging.info(f"处理配置文件时发生错误: {e}")
                                            self.notify_error(f"处理配置文件时发生错误: {e}")
                                    else:
                                        logging.info("未找到'新建'按钮")
                                        self.notify_warning("未找到'新建'按钮，请确认页面是否正确。")
                                except Exception as e:
                                    logging.info(f"'新建'名称时发生错误: {e}")
                                    self.notify_error(f"执行'新建'名称时发生错误: {e}")
                            else:
                                logging.info("用户选择不执行任务，任务取消")

                            # 完成所有操作后询问是否关闭浏览器
                            if self.confirm("操作完成。\n是否关闭浏览器？"):
                                if self.page:
                                    self.close_page()
                                    logging.info("关闭浏览器")
                            else:
                                logging.info("保持浏览器打开状态")
                    except Exception as e:
                        logging.info(f"检测URL时发生错误: {e}")
                        time.sleep(2)

                if not found and not self.stop_flag.is_set():
                    logging.info("等待超时，未检测到预设模块页面URL")

            except Exception as e:
                logging.info(f"打开预设模块页面时发生错误: {e}")
                # 发生错误时关闭浏览器
                if self.page:
                    self.close_page()
                    logging.info("由于错误关闭浏览器")

            return

        # 原有流程 - 处理其他功能
        if not request.config_path:
            self.notify_error("请先生成或选择配置文件")
            logging.info("错误: 未选择配置文件")
            return

        if not self.initialize_chrome_driver():
            return

        try:
            self.page.get("https://pimboss.leycloud.com/")
            logging.info("打开PIMBoss系统")

            try:
                logging.info("请登录PIMBoss，打开文案列表-选择账号配置映射-添加文案字段-选择组件类型")
                logging.info("等待'选项设置'页出现...300秒后超时")

                found = False
                for _ in range(300):
                    if self.stop_flag.is_set():
                        break

                    # 打印页面标题和当前URL

                    # 尝试查找元素并打印结果
                    title_elements = self.page.eles('.ant-modal-title')
                    if title_elements:
                        for ele in title_elements:
                            if "选项设置" in ele.text:
                                found = True
                                break

                    if found:
                        break


                    time.sleep(1)

                if not found:
                    logging.info("未能找到'选项设置'页面，请确认页面是否正确打开")
                    return

                if self.stop_flag.is_set():
                    logging.info("任务被终止")
                    return

                if self.confirm("已到选项设置页，是否进行字段配置？"):
                    logging.info("确认进行字段配置")
                    self.configure_fields(request)
                else:
                    logging.info("取消字段配置")

            except Exception as e:
                logging.info(f"处理过程中发生错误: {e}")
                self.notify_error(f"处理过程中发生错误: {e}")

        except Exception as e:
            logging.info(f"处理过程中发生错误: {e}")
            self.notify_error(f"处理过程中发生错误: {e}")

        finally:
            if self.page:
                self.close_page()
                logging.info("关闭浏览器")

    def configure_fields(self, request):
        logging.info("开始配置字段...")
        wb = openpyxl.load_workbook(request.config_path)
        ws = wb.active
        total_rows = ws.max_row - 1
        success_count = 0
        fail_count = 0
        fail_reasons = []
        start_time = time.time()

        for row in range(2, ws.max_row + 1):
            if self.stop_flag.is_set():
                logging.info("任务被终止")
                break

            try:
                option_name = ws.cell(row=row, column=1).value
                pc_value = ws.cell(row=row, column=2).value if request.fill_pc_value else None
                mobile_value = ws.cell(row=row, column=3).value if request.fill_mobile_value else None
                pc_image = ws.cell(row=row, column=4).value if request.upload_pc_image else None
                mobile_image = ws.cell(row=row, column=5).value if request.upload_mobile_image else None


                # 填写选项名
                name_input = self.page.ele(f'#ComponentType_name{row-2}')
                if name_input:
                    name_input.clear()
                    name_input.input(option_name)

                # 填写PC选项值
                if pc_value:
                    pc_input = self.page.ele(f'#ComponentType_PCValue{row-2}')
                    if pc_input:
                        pc_input.clear()
                        pc_input.input(pc_value)

                # 填写移动选项值
                if mobile_value:
                    mobile_input = self.page.ele(f'#ComponentType_MTValue{row-2}')
                    if mobile_input:
                        mobile_input.clear()
                        mobile_input.input(mobile_value)

                # 上传PC图片
                if pc_image:
                    try:
                        # 先找到PC图片的上传容器
                        upload_wrap = self.page.ele(f'#upload-wrapPCValue{row-2}')
                        if upload_wrap:
                            # 在容器内查找文件上传输入框，使用更精确的选择器
                            file_input = upload_wrap.ele('css:.moxie-shim-html5 > input[type="file"][accept="image/jpeg,image/png"]')
                            if file_input:
                                file_input.input(pc_image)

                                # 等待图片上传完成
                                for _ in range(30):
                                    # 在ant-form-item-children中查找图片
                                    img = self.page.ele(f'css:.ant-form-item-children:has(#upload-wrapPCValue{row-2}) img')
                                    if img:
                                        src = img.attr('src')
                                        if 'kuaimai-sheji-prod' in src:
                                            break
                                    time.sleep(0.5)
                                else:
                                    raise Exception("PC图片上传超时")
                            else:
                                raise Exception("未找到文件上传输入框")
                        else:
                            raise Exception("未找到上传按钮容器")
                    except Exception as e:
                        logging.info(f"PC图片上传失败: {e}")
                        raise

                # 上传移动图片
                if mobile_image:
                    try:
                        # 先找到移动图片的上传容器
                        upload_wrap = self.page.ele(f'#upload-wrapMTValue{row-2}')
                        if upload_wrap:
                            # 在容器内查找文件上传输入框，使用更精确的选择器
                            file_input = upload_wrap.ele('css:.moxie-shim-html5 > input[type="file"][accept="image/jpeg,image/png"]')
                            if file_input:
                                file_input.input(mobile_image)

                                # 等待图片上传完成
                                for _ in range(30):
                                    # 在ant-form-item-children中查找图片
                                    img = self.page.ele(f'css:.ant-form-item-children:has(#upload-wrapMTValue{row-2}) img')
                                    if img:
                                        src = img.attr('src')
                                        if 'kuaimai-sheji-prod' in src:
                                            break
                                    time.sleep(0.5)
                                else:
                                    raise Exception("移动图片上传超时")
                            else:
                                raise Exception("未找到文件上传输入框")
                        else:
                            raise Exception("未找到上传按钮容器")
                    except Exception as e:
                        logging.info(f"移动图片上传失败: {e}")
                        raise

                # 点击新增选项
                if row < ws.max_row:
                    try:
                        # 使用更精确的选择器查找新增选项按钮
                        add_button = self.page.ele('css:.ant-modal-body > div > form + a')
                        if add_button:
                            add_button.click()
                            # 等待一下确保新选项加载完成
                            time.sleep(0.5)
                        else:
                            logging.info("未找到新增选项按钮，尝试其他选择器...")
                            # 尝试其他选择器
                            add_button = self.page.ele('css:.ant-modal-body a:contains("+ 新增选项")')
                            if add_button:
                                add_button.click()
                                time.sleep(0.5)
                            else:
                                logging.info("警告：未能找到新增选项按钮")
                    except Exception as e:
                        logging.info(f"新增选项发生错误: {e}")
                        raise Exception(f"新增选项失败: {e}")

                success_count += 1

            except Exception as e:
                fail_count += 1
                fail_reason = f"行 {row}: {option_name} - {str(e)}"
                fail_reasons.append(fail_reason)
                logging.info(f"任务失败: {fail_reason}")

            time.sleep(0.1)

        end_time = time.time()
        duration = end_time - start_time

        report = TaskReport(
            total_rows, success_count, fail_count, duration,
            failure_details=fail_reasons,
        )
        result_message = format_task_report(report)
        logging.info(result_message)

        if not self.stop_flag.is_set():

            # 使用文本内容查找确定按钮
            confirm_button = self.page.ele('text:确 定')
            if confirm_button:
                confirm_button.click()

                # 等待一段时间，确保操作完成
                time.sleep(2)

                self.notify_info(result_message)
                return  # 不要关闭浏览器，让用户确认结果

        else:
            logging.info("任务被终止")

        # 重置按钮状态和线程
