import json
import hashlib
import random

def generate_config_hash(targets_config, mode, run_name):
    """
    実行設定（ターゲット設定、最適化モード、実行名）から、
    一意のMD5ハッシュ値を計算します。
    """
    config_str = json.dumps(targets_config, sort_keys=True)
    full_string = f"{run_name}-{config_str}-{mode}"
    hasher = hashlib.md5()
    hasher.update(full_string.encode('utf-8'))
    return hasher.hexdigest()

def generate_random_ratios(reagent_count, ratio_sum):
    """
    指定された合計値 (ratio_sum) になる、指定された個数 (reagent_count) の
    0を含まないランダムな整数のリストを生成します。

    Args:
        reagent_count (int): 生成する整数の個数 (t)。
        ratio_sum (int): 生成する整数の合計値 (S)。

    Returns:
        list[int]: 生成された整数のリスト。

    Raises:
        ValueError: 合計値が整数の個数より小さい場合。
    """
    if ratio_sum < reagent_count:
        raise ValueError(f"Ratio sum ({ratio_sum}) cannot be less than the number of reagents ({reagent_count}).")

    dividers = sorted(random.sample(range(1, ratio_sum), reagent_count - 1))

    ratios = []
    last_divider = 0
    for d in dividers:
        ratios.append(d - last_divider)
        last_divider = d
    ratios.append(ratio_sum - last_divider)

    return ratios