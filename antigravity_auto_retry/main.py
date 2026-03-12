import cv2
import numpy as np
import pyautogui
import time
import keyboard  # 用于全局快捷键
from pathlib import Path

# 配置部分
TARGET_DIR = "target_img"
MATCH_THRESHOLD = 0.8  # 匹配相似度阈值
STOP_KEY = "f12"       # 停止脚本的快捷键

# 安全设置：如果鼠标移到屏幕边缘，pyautogui 会抛出异常停止，防止死锁
pyautogui.FAILSAFE = True

def load_targets(target_dir):
    """加载目录下所有图片作为匹配模板"""
    targets = []
    p = Path(target_dir)
    for file_path in list(p.glob("*.png")) + list(p.glob("*.jpg")):
        img = cv2.imread(str(file_path))
        if img is not None:
            targets.append({
                "name": file_path.name,
                "img": img,
                "h": img.shape[0],
                "w": img.shape[1]
            })
    return targets

def match_and_click(screenshot, targets):
    """在截屏中寻找并点击目标"""
    screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    for target in targets:
        # 使用模板匹配
        res = cv2.matchTemplate(screenshot_cv, target["img"], cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= MATCH_THRESHOLD:
            # 计算目标中心点
            center_x = max_loc[0] + target["w"] // 2
            center_y = max_loc[1] + target["h"] // 2
            
            print(f"[{time.strftime('%H:%M:%S')}] 匹配成功: {target['name']} (相似度: {max_val:.2f}) -> 点击坐标: ({center_x}, {center_y})")
            
            # 移动并点击
            pyautogui.click(center_x, center_y)
            # 点击后短暂延迟，防止过快重复点击
            time.sleep(0.5)
            return True  # 每次循环只处理一个目标并立即进入下一次循环/截图
            
    return False

def main():
    print("="*30)
    print(f"快捷键指令: 按下 [{STOP_KEY.upper()}] 停止运行")
    print(f"工作模式: 每秒截图 1 次并寻找目标图片")
    print("="*30)

    targets = load_targets(TARGET_DIR)
    if not targets:
        print(f"错误: '{TARGET_DIR}' 目录下没有任何目标图片！")
        return

    print(f"已加载目标: {[t['name'] for t in targets]}")
    print("脚本已启动，正在监控...")

    try:
        while True:
            # 1. 检查快捷键
            if keyboard.is_pressed(STOP_KEY):
                print(f"\n检测到 [{STOP_KEY.upper()}] 被按下，脚本已安全停止。")
                break

            # 2. 截图与识别
            start_time = time.time()
            screenshot = pyautogui.screenshot()
            
            # 3. 匹配并执行点击
            match_and_click(screenshot, targets)

            # 4. 维持每秒约一次的频率 (除去匹配耗时)
            elapsed = time.time() - start_time
            sleep_time = max(0.1, 1.0 - elapsed)
            time.sleep(sleep_time)

    except Exception as e:
        print(f"\n运行时发生异常: {e}")
    finally:
        print("脚本退出。")

if __name__ == "__main__":
    main()
