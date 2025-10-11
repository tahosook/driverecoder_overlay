#!/usr/bin/env python3
"""
ドライブレコーダー動画合成スクリプト
前方カメラと後方カメラの動画をピクチャーインピクチャーで合成する

使用方法:
  ./overlay.py <前方カメラ動画> <後方カメラ動画>  # 個別ファイル処理
  ./overlay.py <フォルダパス>                     # バッチ処理

出力:
  - ドライブレコーダー形式（251008125706_EF.MP4）の場合: 251008125706_E_overlay.MP4
  - 一般形式の場合: video_overlay.MP4
"""

import os
import sys
import subprocess
import re
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
# 追加インポート
import shutil
from typing import Optional, Tuple, List, Dict

# 定数化: しきい値は上部でまとめて管理
TIME_DIFF_THRESHOLD_SEC = 2      # 前後カメラの最大許容ずれ（秒）
GROUP_TIME_GAP_SEC = 30          # 連続グループ判定の最大間隔（秒）
TIME_DIFF_THRESHOLD = timedelta(seconds=TIME_DIFF_THRESHOLD_SEC)
GROUP_TIME_GAP = timedelta(seconds=GROUP_TIME_GAP_SEC)


def check_ffmpeg():
    """ffmpegコマンドが利用可能か確認する"""
    # shutil.which を使い存在を素早く判定 -> 存在するならバージョン確認
    if shutil.which('ffmpeg') is None:
        return False
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def is_mp4(path: Path) -> bool:
    """拡張子が .mp4/.MP4 かを判定するヘルパー"""
    return path.suffix.lower() == '.mp4'


def parse_filename(filename: str) -> Optional[Tuple[datetime, str, str]]:
    """
    ファイル名から日時、種別、カメラ向きを抽出する
    戻り値: (timestamp, event_type, camera_direction) または None
    """
    base_name = Path(filename).stem

    # パターン: yymmddHHMMss_[種別][カメラ向き]
    pattern = r'^(\d{12})_([A-Z])([FB])$'
    match = re.match(pattern, base_name.upper())  # 大文字化してマッチに強くする

    if match:
        timestamp_str, event_type, camera_direction = match.groups()
        try:
            # YYMMDDHHMMSS -> 20YY-...
            timestamp = datetime.strptime(
                f"20{timestamp_str[:2]}-{timestamp_str[2:4]}-{timestamp_str[4:6]} "
                f"{timestamp_str[6:8]}:{timestamp_str[8:10]}:{timestamp_str[10:12]}",
                "%Y-%m-%d %H:%M:%S"
            )
            return timestamp, event_type, camera_direction
        except ValueError:
            return None

    return None


def generate_output_filename(front_file):
    """
    出力ファイル名を生成する

    Args:
        front_file: 前方カメラのファイルパス

    Returns:
        str: 出力ファイル名
    """
    front_path = Path(front_file)
    front_name = front_path.stem  # 拡張子除去

    # ドライブレコーダー形式かチェック
    parsed = parse_filename(front_path.name)
    if parsed:
        timestamp, event_type, camera_direction = parsed
        # 日時部分 + 種別 + _overlay
        timestamp_str = front_name[:12]  # yymmddHHMMss
        output_name = f"{timestamp_str}_{event_type}_overlay.MP4"
    else:
        # 一般的なファイル形式
        output_name = f"{front_name}_overlay{front_path.suffix}"

    return output_name


def find_pair(front_file: str, files_list: List[str]) -> Optional[str]:
    """
    前方カメラに対応する後方カメラを検索（時間差しきい値を定数参照）
    """
    front_path = Path(front_file)
    front_parsed = parse_filename(front_path.name)
    if not front_parsed:
        return None

    front_timestamp, front_event_type, front_camera_direction = front_parsed
    if front_camera_direction != 'F':
        return None

    best_match = None
    min_time_diff = TIME_DIFF_THRESHOLD  # 定数参照

    for file_path in files_list:
        if file_path == front_file:
            continue

        file_parsed = parse_filename(Path(file_path).name)
        if not file_parsed:
            continue

        file_timestamp, file_event_type, file_camera_direction = file_parsed

        if file_camera_direction == 'B' and file_event_type == front_event_type:
            time_diff = abs(front_timestamp - file_timestamp)
            if time_diff < min_time_diff:
                min_time_diff = time_diff
                best_match = file_path

    return best_match


def set_file_timestamp(file_path, timestamp):
    """
    ファイルのタイムスタンプを設定する

    Args:
        file_path: ファイルパス
        timestamp: datetimeオブジェクト

    Returns:
        bool: 成功したらTrue、失敗したらFalse
    """
    try:
        # timestampをUnix timestampに変換
        unix_timestamp = timestamp.timestamp()
        # アクセス時刻と修正時刻の両方を設定
        os.utime(file_path, (unix_timestamp, unix_timestamp))
        return True
    except OSError as e:
        print(f"警告: タイムスタンプ設定に失敗しました: {e}")
        return False


def concat_videos(video_files: List[str], output_file: str) -> bool:
    """
    複数の動画ファイルを連結する（呼び出し挙動は変えない）
    """
    if len(video_files) < 2:
        print("エラー: 連結には2つ以上の動画ファイルが必要です")
        return False

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_list_file = f.name
        for video_file in video_files:
            abs_path = os.path.abspath(video_file)
            f.write(f"file '{abs_path}'\n")

    try:
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', temp_list_file,
            '-c', 'copy',
            output_file
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"エラー: 動画連結に失敗しました - {e}")
        if e.stderr:
            print(f"詳細: {e.stderr}")
        return False
    finally:
        try:
            os.unlink(temp_list_file)
        except OSError:
            pass


def find_consecutive_groups(overlay_files: List[str]) -> List[Dict]:
    """
    連続した_overlayファイルをグループ化する
    GROUP_TIME_GAP 定数を参照して間隔判定を行う
    """
    groups = []
    if not overlay_files:
        return groups

    overlay_info = []
    for file_path in overlay_files:
        file_name = Path(file_path).name
        if '_overlay' in file_name and file_name.upper().endswith('.MP4'):
            base_name = file_name.replace('_overlay.MP4', '')
            parts = base_name.split('_')
            if len(parts) >= 2:
                timestamp_str = parts[0]
                event_type = parts[1]
                try:
                    timestamp = datetime.strptime(
                        f"20{timestamp_str[:2]}-{timestamp_str[2:4]}-{timestamp_str[4:6]} "
                        f"{timestamp_str[6:8]}:{timestamp_str[8:10]}:{timestamp_str[10:12]}",
                        "%Y-%m-%d %H:%M:%S"
                    )
                    overlay_info.append({
                        'path': file_path,
                        'timestamp': timestamp,
                        'event_type': event_type,
                        'base_name': base_name
                    })
                except ValueError:
                    continue

    overlay_info.sort(key=lambda x: x['timestamp'])

    current_group = None
    for info in overlay_info:
        if current_group is None:
            current_group = {
                'files': [info],
                'event_type': info['event_type'],
                'start_time': info['timestamp'],
                'last_time': info['timestamp']
            }
        else:
            time_diff = info['timestamp'] - current_group['last_time']
            if time_diff <= GROUP_TIME_GAP and info['event_type'] == current_group['event_type']:
                current_group['files'].append(info)
                current_group['last_time'] = info['timestamp']
            else:
                if len(current_group['files']) >= 2:
                    groups.append({
                        'files': [item['path'] for item in current_group['files']],
                        'event_type': current_group['event_type'],
                        'start_time': current_group['start_time']
                    })
                current_group = {
                    'files': [info],
                    'event_type': info['event_type'],
                    'start_time': info['timestamp'],
                    'last_time': info['timestamp']
                }

    if current_group and len(current_group['files']) >= 2:
        groups.append({
            'files': [item['path'] for item in current_group['files']],
            'event_type': current_group['event_type'],
            'start_time': current_group['start_time']
        })

    return groups


def run_ffmpeg(front_file, back_file, output_file):
    """
    ffmpegコマンドを実行して合成処理を行う

    Args:
        front_file: 前方カメラファイルパス
        back_file: 後方カメラファイルパス
        output_file: 出力ファイルパス

    Returns:
        tuple: (bool, datetime or None) - 成功したらTrueと前方カメラのタイムスタンプ、失敗したらFalseとNone
    """
    # 前方カメラファイルのタイムスタンプを取得
    front_timestamp = None
    front_parsed = parse_filename(Path(front_file).name)
    if front_parsed:
        front_timestamp = front_parsed[0]

    # ffmpegコマンドの構築
    cmd = [
        'ffmpeg',
        '-i', front_file,
        '-i', back_file,
        '-filter_complex',
        '[0:v]crop=iw:ih*0.9[v0];[1:v]scale=iw/2.5:ih/2.5,crop=iw:ih*0.66[v1];[v0][v1]overlay=W-w-20:H-h-70[v]',
        '-map', '[v]',
        '-map', '0:a',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-crf', '23',
        '-c:a', 'copy',
        '-shortest',
        output_file
    ]

    try:
        # サブプロセス実行
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # 出力ファイルのタイムスタンプを設定
        if front_timestamp and os.path.exists(output_file):
            set_file_timestamp(output_file, front_timestamp)

        return True, front_timestamp
    except subprocess.CalledProcessError as e:
        print(f"エラー: ffmpeg処理に失敗しました - {e}")
        if e.stderr:
            print(f"詳細: {e.stderr}")
        return False, None


def process_single_pair(front_file, back_file):
    """
    個別ファイルペアの処理を行う

    Args:
        front_file: 前方カメラファイルパス
        back_file: 後方カメラファイルパス

    Returns:
        bool: 成功したらTrue、失敗したらFalse
    """
    # ファイル存在チェック
    if not os.path.exists(front_file):
        print(f"エラー: 前方カメラファイルが見つかりません: {front_file}")
        return False

    if not os.path.exists(back_file):
        print(f"エラー: 後方カメラファイルが見つかりません: {back_file}")
        return False

    # 出力ファイル名生成
    output_filename = generate_output_filename(front_file)
    output_file = os.path.join(os.path.dirname(front_file), output_filename)

    # 出力ファイルが既に存在するかチェック
    if os.path.exists(output_file):
        print(f"スキップ: 出力ファイルが既に存在します: {output_file}")
        return True

    print(f"処理中: {os.path.basename(front_file)} + {os.path.basename(back_file)} -> {output_filename}")

    # ffmpeg実行
    success, timestamp = run_ffmpeg(front_file, back_file, output_file)
    if success:
        if timestamp:
            print(f"完了: {output_filename} (タイムスタンプ設定済み)")
        else:
            print(f"完了: {output_filename}")
        return True
    else:
        return False


def process_batch(directory):
    """
    バッチ処理モードでフォルダ内のファイルを処理する

    Args:
        directory: 処理対象のディレクトリパス

    Returns:
        tuple: (処理総数, 成功数, エラー数)
    """
    directory_path = Path(directory)

    if not directory_path.is_dir():
        print(f"エラー: 指定されたパスはディレクトリではありません: {directory}")
        return 0, 0, 0

    # MP4ファイルの一覧を取得
    mp4_files = list(directory_path.glob('*.MP4')) + list(directory_path.glob('*.mp4'))
    if not mp4_files:
        print(f"警告: 指定ディレクトリにMP4ファイルが見つかりません: {directory}")
        return 0, 0, 0

    mp4_files = [str(f) for f in mp4_files]  # Pathオブジェクトを文字列に変換

    print(f"バッチ処理開始: {directory_path.name} ({len(mp4_files)}個のMP4ファイル)")

    processed = 0
    successful = 0
    errors = 0

    # 前方カメラファイルのみ処理
    front_files = []
    for file_path in mp4_files:
        parsed = parse_filename(Path(file_path).name)
        if parsed and parsed[2] == 'F':  # カメラ向きが'F'（前方）
            front_files.append(file_path)

    if not front_files:
        print("警告: 前方カメラファイル（*_F.MP4）が1つも見つかりません")
        return 0, 0, 0

    for front_file in front_files:
        processed += 1

        # 対応する後方カメラファイルを検索
        back_file = find_pair(front_file, mp4_files)

        if not back_file:
            print(f"警告: ペアとなる後方カメラが見つかりません: {os.path.basename(front_file)}")
            errors += 1
            continue

        # 処理実行
        if process_single_pair(front_file, back_file):
            successful += 1
        else:
            errors += 1

    # 動画連結処理
    print("\n動画連結処理を開始...")
    overlay_files = list(directory_path.glob('*_overlay.MP4'))

    if overlay_files:
        # 連続グループを検索
        consecutive_groups = find_consecutive_groups([str(f) for f in overlay_files])

        if consecutive_groups:
            print(f"連続グループ数: {len(consecutive_groups)}")

            merged_count = 0
            for i, group in enumerate(consecutive_groups):
                group_files = group['files']
                event_type = group['event_type']

                if len(group_files) >= 2:
                    # 最初のファイルの名前を基準に連結ファイル名を生成
                    first_file_path = group_files[0]
                    first_file_name = Path(first_file_path).name
                    base_name = first_file_name.replace('_overlay.MP4', '')
                    merged_filename = f"{base_name}_overlay_merged.MP4"
                    merged_file_path = os.path.join(directory, merged_filename)

                    print(f"グループ {i+1}: {len(group_files)}個のファイルを連結中...")
                    for file_path in group_files:
                        print(f"  - {os.path.basename(file_path)}")

                    # 動画連結実行
                    if concat_videos(group_files, merged_file_path):
                        print(f"完了: {merged_filename}")

                        # タイムスタンプを設定（最初のファイルのタイムスタンプを使用）
                        if group['start_time']:
                            set_file_timestamp(merged_file_path, group['start_time'])

                        # 個別のファイルを削除
                        for file_path in group_files:
                            try:
                                os.unlink(file_path)
                                print(f"削除: {os.path.basename(file_path)}")
                            except OSError as e:
                                print(f"警告: ファイル削除に失敗: {os.path.basename(file_path)} - {e}")

                        merged_count += 1
                    else:
                        print(f"エラー: 連結に失敗: {merged_filename}")
                else:
                    print(f"グループ {i+1}: 連結条件を満たさないためスキップ (ファイル数: {len(group_files)})")

            print(f"動画連結処理完了: {merged_count}個のファイルグループを連結")
        else:
            print("連続する動画ファイルが見つかりませんでした")
    else:
        print("連結対象の_overlayファイルが見つかりませんでした")

    print(f"\nバッチ処理完了: 総数 {processed}, 成功 {successful}, エラー {errors}")
    return processed, successful, errors


def main():
    """メイン処理"""
    # 引数チェックを最初に行う
    if len(sys.argv) == 1:
        print("Usage: ./overlay.py <front_camera_video> <rear_camera_video> or ./overlay.py <folder_path>")
        sys.exit(0)

    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("使用方法: ./overlay.py <前方カメラ動画> <後方カメラ動画> または ./overlay.py <フォルダパス>")
        sys.exit(1)

    # ffmpegの存在確認
    if not check_ffmpeg():
        print("Error: ffmpeg not found. Please install with: brew install ffmpeg")
        sys.exit(1)

    # 個別ファイル処理モード
    if len(sys.argv) == 3:
        front_file = sys.argv[1]
        back_file = sys.argv[2]
        success = process_single_pair(front_file, back_file)
        sys.exit(0 if success else 1)

    # バッチ処理モード
    elif len(sys.argv) == 2:
        directory = sys.argv[1]
        processed, successful, errors = process_batch(directory)
        sys.exit(0 if errors == 0 else 1)


if __name__ == '__main__':
    main()
