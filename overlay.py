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
from pathlib import Path
from datetime import datetime, timedelta


def check_ffmpeg():
    """ffmpegコマンドが利用可能か確認する"""
    try:
        subprocess.run(['ffmpeg', '-version'],
                      capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def parse_filename(filename):
    """
    ファイル名から日時、種別、カメラ向きを抽出する

    Args:
        filename: ファイル名（拡張子含む）

    Returns:
        tuple: (timestamp, event_type, camera_direction) または None
    """
    # 拡張子を除去してファイル名のみ取得
    base_name = Path(filename).stem

    # 正規表現パターン: yymmddHHMMss_[種別][カメラ向き]
    # yy: 年下2桁, mm: 月, dd: 日, HH: 時, MM: 分, SS: 秒
    # 種別: 英大文字（E, Uなど）
    # カメラ向き: F(前) or B(後)
    pattern = r'^(\d{12})_([A-Z])([FB])$'
    match = re.match(pattern, base_name)

    if match:
        timestamp_str, event_type, camera_direction = match.groups()
        # 日時文字列をdatetimeオブジェクトに変換
        # YYMMDDHHMMSS -> 20YY-MM-DD HH:MM:SS
        try:
            full_year = f"20{timestamp_str[:2]}"
            month = timestamp_str[2:4]
            day = timestamp_str[4:6]
            hour = timestamp_str[6:8]
            minute = timestamp_str[8:10]
            second = timestamp_str[10:12]
            timestamp = datetime.strptime(
                f"{full_year}-{month}-{day} {hour}:{minute}:{second}",
                "%Y-%m-%d %H:%M:%S"
            )
            return timestamp, event_type, camera_direction
        except ValueError:
            pass

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


def find_pair(front_file, files_list):
    """
    前方カメラファイルに対応する後方カメラファイルを検索する

    Args:
        front_file: 前方カメラのファイルパス
        files_list: 検索対象のファイルリスト

    Returns:
        str or None: 対応する後方カメラファイルのパス、見つからない場合はNone
    """
    front_path = Path(front_file)
    front_name = front_path.name

    # 前方カメラファイルの情報を取得
    front_parsed = parse_filename(front_name)
    if not front_parsed:
        # ドライブレコーダー形式でない場合はペアリングなし
        return None

    front_timestamp, front_event_type, front_camera_direction = front_parsed

    # F以外は前方カメラではない
    if front_camera_direction != 'F':
        return None

    best_match = None
    min_time_diff = timedelta(seconds=2)  # 1秒以内のずれを許容

    for file_path in files_list:
        if file_path == front_file:
            continue  # 自分自身は除外

        file_name = Path(file_path).name
        file_parsed = parse_filename(file_name)

        if not file_parsed:
            continue  # ドライブレコーダー形式でないファイルは除外

        file_timestamp, file_event_type, file_camera_direction = file_parsed

        # カメラ向きが後方(B)で、種別が一致する場合のみ候補
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
