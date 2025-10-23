# 実行名を定義します。出力ディレクトリの名前の一部として使用されます。
RUN_NAME = "manual-check"
# 混合ツリーの階層構造（factors）を決定するモードを選択します。
# 'manual': TARGETS_FOR_MANUAL_MODE で定義された factors を手動で設定します。
# 'auto': 各ターゲットの ratios の合計値から factors を自動計算します。
# 'auto_permutations': 'auto' で計算された factors の全順列を試し、最適な階層構造を探します。
# 'random': RANDOM_SETTINGS に基づいてランダムなシナリオを複数回実行します。
FACTOR_EXECUTION_MODE = "manual"
# 最適化の目的を設定します。
# "waste": 廃棄物量の最小化を目指します。
# "operations": 混合操作の総回数の最小化を目指します。
# "reagents": 総試薬使用量の最小化を目指します。
OPTIMIZATION_MODE = "waste"
# チェックポイント機能を有効にするかどうかを設定します。Trueにすると、中断された計算を再開できます。
ENABLE_CHECKPOINTING = False

# --- 制約条件 ---

# ノード間で共有（中間液を融通）できる液量の最大値を設定します。Noneの場合は無制限です。
MAX_SHARING_VOLUME = None
# 中間液を共有する際の、供給元と供給先の階層レベル（level）の差の最大値を設定します。Noneの場合は無制限です。
MAX_LEVEL_DIFF = None
# 1回の混合操作で使用できるミキサーの最大容量（入力の合計値）を設定します。これはDFMMアルゴリズムで混合ツリーの階層を決定する際の因数の最大値にもなります。
MAX_MIXER_SIZE = 5

# --- 'random' モード用設定 ---
# FACTOR_EXECUTION_MODE が 'random' の場合にのみ使用されます。
RANDOM_SETTINGS = {
    't_reagents': 3,       # ランダムシナリオにおける試薬の種類数。
    'n_targets': 3,        # ランダムシナリオにおけるターゲット（目標混合液）の数。
    'k_runs': 30,           # 生成・実行するランダムシナリオの総数。

    # --- 混合比和の生成ルール（以下の優先順位で適用されます） ---
    # 優先度1: 固定シーケンス（n_targetsと要素数を一致させる必要あり）
    # 18*5' と書くと「合計18の混合比を生成し、各要素を5倍する」というロジックが適用
    # 例： 'S_ratio_sum_sequence': [18, 18*5, 25]
    

    # 優先度2: 候補リストからのランダム選択
    # sequenceが空の場合にこちらが評価されます。ターゲット毎にこのリストからランダムに値が選ばれます。
    # 例： 'S_ratio_sum_candidates': [18, 24, 30, 36]
    # 'S_ratio_sum_candidates': [18, 24, 30, 36],

    # 優先度3: 上記2つが有効でない場合のデフォルト値
    'S_ratio_sum': 18,
}
# --- 'auto' / 'auto_permutations' モード用設定 ---
# FACTOR_EXECUTION_MODE が 'auto' または 'auto_permutations' の場合に使用されます。
# 'factors' を指定する必要はありません。自動で計算されます。
TARGETS_FOR_AUTO_MODE = [
    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122]},
    # {'name': 'Target 1', 'ratios': [2, 3, 7]},
    # {'name': 'Target 2', 'ratios': [1, 5, 6]},
    # {'name': 'Target 3', 'ratios': [4, 3, 5]},
    # {'name': 'Target 1', 'ratios': [45, 26, 64]},
    {'name': 'Target 1', 'ratios': [1,8,9]},
    {'name': 'Target 2', 'ratios': [2,1,15]},
    {'name': 'Target 2', 'ratios': [3,4,11]},
    {'name': 'Target 2', 'ratios': [6,7,5]},
    
    # {'name': 'Target 3', 'ratios': [3, 5, 10]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36]},
    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122]},
    # {'name': 'Target 1', 'ratios': [15, 18, 42]}
]

# --- 'manual' モード用設定 ---
# FACTOR_EXECUTION_MODE が 'manual' の場合に使用されます。
# 'factors'（混合階層）を各ターゲットに対して手動で指定する必要があります。
# 'ratios'の合計値と'factors'の積は一致している必要があります。
TARGETS_FOR_MANUAL_MODE = [
    # {'name': 'Target 1', 'ratios': [45, 26, 64], 'factors': [3, 3, 3, 5]},
    # {'name': 'Target 2', 'ratios': [80, 26, 29], 'factors': [3, 3, 3, 5]},
    # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [3, 5, 3, 2]},
    # {'name': 'Target 1', 'ratios': [6, 33, 15], 'factors': [3, 3, 3, 2]},
    # {'name': 'Target 1', 'ratios': [2, 3, 7], 'factors': [3, 2, 2]},
    # {'name': 'Target 2', 'ratios': [1, 5, 6], 'factors': [3, 2, 2]},
    # {'name': 'Target 3', 'ratios': [4, 3, 5], 'factors': [3, 2, 2]},
    # {'name': 'Target 3', 'ratios': [4, 5, 9], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [3, 5, 10], 'factors': [3, 3, 2]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4], 'factors': [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36], 'factors': [3, 5, 5]},

    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122], 'factors': [4, 4, 4, 4]},
    # {'name': 'Target 1', 'ratios': [2, 11, 5], 'factors': [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [12, 5, 1], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},

    {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [5, 3, 3, 2]},
    {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
    {'name': 'Target 3', 'ratios': [15, 18, 42], 'factors': [3, 5, 5]}
]