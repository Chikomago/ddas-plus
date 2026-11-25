// Version history shown by the "更新内容" button next to Settings.
// Keep the first entry's version in sync with plugin.json / APP_VERSION.
export const CHANGELOG = [
  {
    title: 'v2.0.11',
    version: '2.0.11',
    items: ['修复 Windows 构建测试的编码和路径兼容问题'],
  },
  {
    title: 'v2.0.10',
    version: '2.0.10',
    items: [
      '前端pyttk重构为webview',
      '重新设计交互',
      '多字段配置时自动启用多线程多标签并行配置',
      '支持PC图移动图分别添加',
      '针对配置文件生成和编辑体验优化',
      '优化违禁词/内容填充/图片回填/保存结果校验的健壮性',
      '新增修改选项表单功能，可选跳过/修改',
      '安全考虑,不再提供明文账号密码保存及自动登录'
    ],
  },
  {
    title: 'v1.3.10',
    version: '1.3.10',
    items: ['新增 Intel 芯片 macOS 构建'],
  },
  {
    title: 'v1.3.9',
    version: '1.3.9',
    items: ['修复 Windows 下字段布局', '窗口标题显示应用版本号'],
  },
  {
    title: 'v1.3.8',
    version: '1.3.8',
    items: ['修复 Windows 插件构建输出编码'],
  },
];
