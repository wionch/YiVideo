
## 功能概述
实现一站式视频自动生成, 分发发布的工具
## 功能特点
模块化, 可插拔式
### docker部署
通过windows docker desktop + wsl2进行部署
主要解决:
进行环境隔离
解决cuda和cudnn的部署问题
### 支持异步API接口
每个功能块都支持通过接口来实现
异步后台执行逻辑:
请求一个任务id
后台执行任务
请求任务id获取任务状态和数据
## 核心功能列表
### 视频翻译
* 视频下载
	* youtube视频下载
		使用`yt-dlp`等工具进行下载
	* m3u8视频下载
		使用m3u8格式下载工具下载视频. 如`N_m3u8DL-CLI`
* 获取字幕
	最终返回包括: 时间区间 + 字幕文本 的json和srt文件
	如果是ocr识别: 添加`字幕位置区间(x1, y1, x2, y2)`数据到json文件中
	如果是whisperx转录识别:  添加`说话人`数据到json文件中
	* OCR识别获取字幕
		利用ocr识别技术,将视频帧中的字幕识别出来.
		传统模式: 逐帧识别.
		但是, 非必要情况下, 不建议进行进行逐帧识别. 效率低, 性能损耗大.
		优化工作流:
		先确定字幕区域, 这样就可以处理字幕区域而不用进行全帧处理, 可以减少ocr识别带来的开销;
		确定字幕关键帧. 确定并只识别字幕第一帧. 减少重复识别操作
		识别字幕条, 最大可能排除其他因素. 提高识别精准度, 提高识别效率
		OCR工具: PaddleOCR
		经过横向比对和实测, PaddleOCR在识别精准度上和但图片识别效率上都比其他(EasyOCR)要快, 识别精准度更高.
		缺点: 实测无法实现并发ocr, 官网上有说高性能部署方案, 但是实操难度大, 测试过很久都无法部署成功, 后续如果卡在性能上再去尝试部署. 也有可能是商家想要用户去使用他们的付费api.
		* 执行流程
			* 确定字幕区域
				这里如果没有获取到字幕区域, 就表示该视频可能没有字幕
				后续对于字幕的相关工作则停止.
				只能通过转录方式去获取字幕了
				* 视频帧采样
				* ocr识别这些视频帧
				* 通过算法确定字幕的稳定区域
					获取所有识别结果
					字数长的进行加权, 字数短的进行减权
					最终根据比例算出字幕区域
			* 获取字幕帧
				根据`dash`和`像素标准差`识别字幕关键帧确定出来. 减少重复识别.
				整体逻辑是根据字幕区域中画像进行判断,如果突然相邻两帧的变化很大, 大概率就是字幕发生变化. 如果某一段时间区间中的变化不大, 就说这一段视频帧都是同一个字幕.

				所以只需要取第一帧为字幕关键帧.  这样可以省略大量的重复的OCR识别工作.
			* ocr识别字幕
				结合字幕关键帧 + 字幕区域进行OCR识别, 得到准确的字幕内容.
				同时可以根据帧数 + 视频时长 + 视频帧率反推出字幕时间
		* OCR工具: PaddleOCR
			* 优点
				* 识别准确率高
					相较于其他ocr模块, 如 : easyocr 识别准确率要高.
				* 单张识别速度快
				* 支持混合语言识别
					支持中英文或其他语言混合识别
			* 缺点
				* 暂无法实现并发ocr处理
					官网提供了高并发部署方案, 但是实测部署过几次, 都没有办法成功. 暂时搁置. 后续需要性能方面的处理, 再去研究部署.
					参考官方提供的多进程并发代码样例来实现并发
		* 优化思路
			* 多张图片合并成一张, 减少ocr次数
				3-5张图片合并成1张. 只需要ocr识别1次即可. 然后根据每张图片高度和识别结果的坐标可以将所有识别结果反推在各自每张图片上的实际坐标
				如: 3张100x200的图片纵向合并识别结果如下:
				A坐标: 20 x 14
				B坐标: 65 x345
				C坐标: 77 x 566
				反推出:
				A坐标: 第一张图的20x14
				B坐标: 第二张图的65x145
				C坐标: 第三张图的77x166
			* 使用进程并发. 提高ocr速度
				还是确定使用多进程并发, 提高速度.
				api接口方式暂时不用, 只支持uvicorn异步线程. 并不支持多并发
				减少部署难度
				提高部署成功率
				环境隔离
				提供api接口, 覆盖更多应用和场景
	* 音频转录获取字幕
		参考VideoLingo项目
		* 使用`ffmpeg`分离视频和音轨
		* 通过`Demucs`将音轨分离成人声+背景音
		* 通过`whisperx`将人声转录成字幕文件(时间区间 + 字幕文本 + 说话人)
* 字幕翻译
	翻译功能参考VideoLingo项目
	详见: `VideoLingo 翻译功能逻辑与工作流详解`
	* 字幕校正
		* 错别字, 语法纠正
			ocr和语音转录的字幕文本会有错别字的情况, 尤其是语音转录, 错别字的情况还比较多.  所以需要进行一次校正
	* 翻译字幕
		* 文本预处理和分块
		* 提供上下文翻译
		* 两步翻译法
		* 结果整合和时间戳对齐
	* 字幕校正
		* 翻译结果校正
		* 字幕长度优化
* 视频去除硬字幕
	根据前面获取的字幕文件, 根据字幕时间戳, 位置进行字幕消除处理. 参考`video-subtitle-remover`模块
* 生成语音
	* 使用indextts基于字幕文件生成对应语音
	* 使用GPT-SoVITS基于字幕文件生成对应的语音
* 合并视频
	* 原视频(无音轨) + 字幕文件 + 新语音 + 背景音 合并成最终的新的视频
### 全自动生成视频
* 确定视频主题
* 生成视频脚本
	* 字幕脚本
	* 分镜脚本
* 生成视频
	* 生成分镜视频
	* 合并视频
### 自动发布(YiDigit)
利用chrome自动化扩展YiMCP. 设计脚本. 将视频, 文本, 图片自动发布到包括youtube, tiktok, instagram, x, 微博, 小红书, 抖音, 快手, b站等自媒体网站.
多chrome实例实现多账号管理. 比如: 利用比特浏览器等其他指纹浏览器可以实现N个浏览器实例 登录N个自媒体平台, 管理N个自媒体账号.
## 前端功能
### 任务管理
* 任务列表
* 任务编辑
	* 说话人截取功能
### 素材管理
* 素材列表
* 导入素材
* 素材编辑
### 用户管理
* 用户信息
* AI接口管理
## 关联项目
```
### [VideoLingo: 一站式视频翻译本地化配音工具](https://github.com/Huanshere/VideoLingo)
### [yt-dlp: youtube视频下载工具](https://github.com/yt-dlp/yt-dlp)
### [PaddleOCR: 业界领先、可直接部署的 OCR 与文档智能引擎](https://github.com/PaddlePaddle/PaddleOCR)
### [Video-subtitle-remover (VSR):  是一款基于AI技术，将视频中的硬字幕去除的软件](https://github.com/YaoFANGUK/video-subtitle-remover)
### [python-audio-separator: 负责音频中人声和非人声（背景音乐、环境音）的精确分离。它通过加载 ](https://github.com/nomadkaraoke/python-audio-separator)`[UVR (Ultimate Vocal Remover)](https://github.com/nomadkaraoke/python-audio-separator)`[ 的 ](https://github.com/nomadkaraoke/python-audio-separator)`[MDX-Net](https://github.com/nomadkaraoke/python-audio-separator)`[ 模型，能够高效地处理复杂音频](https://github.com/nomadkaraoke/python-audio-separator)
### [FFmpeg: FFmpeg处理多媒体内容（如音频、视频、字幕和相关元数据）的库和工具的集合](https://github.com/FFmpeg/FFmpeg)
### [WhisperX: 提供快速的自动语音识别（使用large-v2时实时性为70倍），具有单词级时间戳和说话人分离功能](https://github.com/m-bain/whisperX)
### [IndexTTS: 一种工业级可控高效的文转语音系统](https://github.com/RVC-Boss/GPT-SoVITS)
### [GPT-SoVITS: 强大的少样本语音转换与语音合成Web用户界面.](https://github.com/RVC-Boss/GPT-SoVITS)
### [MoneyPrinterTurbo: 全自动生成视频文案、视频素材、视频字幕、视频背景音乐，然后合成一个高清的短视频](https://github.com/harry0703/MoneyPrinterTurbo)
```