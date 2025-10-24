import json
import hashlib
import random
import re

# --- キー生成・解析関数 (docstring追加) ---

KEY_INTRA_PREFIX = "l"
KEY_INTER_PREFIX = "t"
KEY_PEER_PREFIX = "R_idx"


def create_dfmm_node_name(target_idx, level, node_idx):
    """DFMMノードのグローバル名を生成します。

    Args:
        target_idx (int): ターゲットのインデックス。
        level (int): ノードのレベル。
        node_idx (int): レベル内でのノードのインデックス。

    Returns:
        str: グローバルノード名 (例: 'mixer_t0_l1_k0')。
    """
    return f"mixer_t{target_idx}_l{level}_k{node_idx}"


def create_intra_key(level, node_idx):
    """ツリー内共有キーの本体部分を生成します。
       ('from_' プレフィックスは含まない)

    Args:
        level (int): 供給元ノードのレベル。
        node_idx (int): 供給元ノードのインデックス。

    Returns:
        str: 内部共有キー (例: 'l1k0')。
    """
    return f"{KEY_INTRA_PREFIX}{level}k{node_idx}"


def create_inter_key(target_idx, level, node_idx):
    """ツリー間共有キーの本体部分を生成します。
       ('from_' プレフィックスは含まない)

    Args:
        target_idx (int): 供給元ノードのターゲットインデックス。
        level (int): 供給元ノードのレベル。
        node_idx (int): 供給元ノードのインデックス。

    Returns:
        str: 外部共有キー (例: 't0_l1k0')。
    """
    return f"{KEY_INTER_PREFIX}{target_idx}_l{level}k{node_idx}"


def create_peer_key(peer_idx):
    """ピア(R)ノード共有キーの本体部分を生成します。
       ('from_' プレフィックスは含まない)

    Args:
        peer_idx (int): ピア(R)ノードのインデックス。

    Returns:
        str: ピア共有キー (例: 'R_idx0')。
    """
    return f"{KEY_PEER_PREFIX}{peer_idx}"


def parse_sharing_key(key_str_no_prefix):
    """
    共有キー文字列 ('from_' を除いた本体部分) を解析し、
    供給元の種類とインデックス情報を辞書で返します。

    Args:
        key_str_no_prefix (str): 'from_' を除いたキー文字列。

    Returns:
        dict: 解析結果。キーは 'type' ('PEER', 'DFMM', 'INTRA') と、
              タイプに応じたインデックス ('idx', 'target_idx', 'level', 'node_idx')。

    Raises:
        ValueError: 未知のキー形式の場合。
    """
    if key_str_no_prefix.startswith(KEY_PEER_PREFIX):
        return {
            "type": "PEER",
            "idx": int(key_str_no_prefix.replace(KEY_PEER_PREFIX, "")),
        }

    elif key_str_no_prefix.startswith(KEY_INTER_PREFIX):
        match = re.match(r"t(\d+)_l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            return {
                "type": "DFMM",
                "target_idx": int(match.group(1)),
                "level": int(match.group(2)),
                "node_idx": int(match.group(3)),
            }

    elif key_str_no_prefix.startswith(KEY_INTRA_PREFIX):
        match = re.match(r"l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            return {
                "type": "INTRA",
                "level": int(match.group(1)),
                "node_idx": int(match.group(2)),
            }

    # 解析できなかった場合はエラー
    raise ValueError(f"Unknown sharing key format: {key_str_no_prefix}")


def generate_config_hash(targets_config, mode, run_name):
    """
    実行設定から一意のMD5ハッシュ値を計算します。
    """
    config_str = json.dumps(targets_config, sort_keys=True)
    full_string = f"{run_name}-{config_str}-{mode}"
    hasher = hashlib.md5()
    hasher.update(full_string.encode("utf-8"))
    return hasher.hexdigest()


def generate_random_ratios(reagent_count, ratio_sum):
    """
    指定された合計値になる、指定された個数の
    0を含まないランダムな整数のリストを生成します。
    """
    if ratio_sum < reagent_count:
        raise ValueError(
            f"Ratio sum ({ratio_sum}) cannot be less than the number of reagents ({reagent_count})."
        )

    dividers = sorted(random.sample(range(1, ratio_sum), reagent_count - 1))

    ratios = []
    last_divider = 0
    for d in dividers:
        ratios.append(d - last_divider)
        last_divider = d
    ratios.append(ratio_sum - last_divider)

    return ratios
