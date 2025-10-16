# utils/helpers.py
import json
import hashlib
import random

def generate_config_hash(targets_config, mode, run_name):
    """
    実行設定（ターゲット設定、最適化モード、実行名）から、
    一意のMD5ハッシュ値を計算します。
    このハッシュは、チェックポイントファイル名や出力ディレクトリ名に使用され、
    同じ設定での実行を識別するために役立ちます。

    Args:
        targets_config (list): ターゲット設定のリスト。
        mode (str): 最適化モード ('waste' or 'operations')。
        run_name (str): 実行名。

    Returns:
        str: 計算された16進数のハッシュ文字列。
    """
    # 辞書の順序に依存しないように、キーでソートしてJSON文字列に変換
    config_str = json.dumps(targets_config, sort_keys=True)
    # 全ての情報を結合した単一の文字列を作成
    full_string = f"{run_name}-{config_str}-{mode}"

    # MD5ハッシュオブジェクトを作成
    hasher = hashlib.md5()
    # 文字列をUTF-8エンコードしてハッシュを更新
    hasher.update(full_string.encode('utf-8'))
    # 16進数表現のハッシュ値を取得して返す
    return hasher.hexdigest()

def generate_random_ratios(reagent_count, ratio_sum):
    """
    指定された合計値 (ratio_sum) になる、指定された個数 (reagent_count) の
    0を含まないランダムな整数のリストを生成します。
    'random' モードで、テスト用のターゲット比率を生成するために使用されます。

    例: generate_random_ratios(3, 10) -> [2, 3, 5], [1, 1, 8] など

    Args:
        reagent_count (int): 生成する整数の個数 (t)。
        ratio_sum (int): 生成する整数の合計値 (S)。

    Returns:
        list[int]: 生成された整数のリスト。

    Raises:
        ValueError: 合計値が整数の個数より小さい場合（0を含まないため）。
    """
    if ratio_sum < reagent_count:
        raise ValueError("Ratio sum (S) cannot be less than the number of reagents (t).")

    # S-1個の可能な区切り位置から、t-1個のユニークな区切り点をランダムに選ぶ
    dividers = sorted(random.sample(range(1, ratio_sum), reagent_count - 1))

    ratios = []
    last_divider = 0
    # 区切り点を使って、リストの各要素を計算
    for d in dividers:
        ratios.append(d - last_divider)
        last_divider = d
    # 最後の要素を追加
    ratios.append(ratio_sum - last_divider)

    return ratios