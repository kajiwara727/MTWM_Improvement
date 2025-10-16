# core/dfmm.py
import math
import itertools
from functools import reduce
import operator

def find_factors_for_sum(ratio_sum, max_factor):
    """
    DFMM (Digital Microfluidic Mixing) アルゴリズムに基づき、比率の合計値（ratio_sum）を
    指定された最大値（max_factor）以下の因数の積に分解します。
    これは、混合ツリーの階層構造を決定するために使用されます。

    Args:
        ratio_sum (int): 分解対象となる比率の合計値。
        max_factor (int): 許容される因数の最大値。

    Returns:
        list[int] or None: 見つかった因数のリスト（降順ソート済み）。見つからない場合はNone。
    """
    if ratio_sum <= 1: return []
    n, factors = ratio_sum, []
    while n > 1:
        found_divisor = False
        # 効率化のため、大きな因数から試す
        for d in range(max_factor, 1, -1):
            if n % d == 0:
                factors.append(d)
                n //= d
                found_divisor = True
                break
        # どの因数でも割り切れなかった場合、分解は不可能
        if not found_divisor:
            print(f"Error: Could not find factors for sum {ratio_sum}. Failed at {n}.")
            return None
    return sorted(factors, reverse=True)

def generate_unique_permutations(factors):
    """
    因数のリストから、重複を考慮したユニークな順列をすべて生成します。
    'auto_permutations' モードで、最適な混合階層の順序を探索するために使用されます。

    Args:
        factors (list[int]): 因数のリスト。

    Returns:
        list[tuple]: 生成されたユニークな順列のリスト。
    """
    if not factors:
        return [()]
    # set を使うことで、同じ順列が複数回現れるのを防ぐ (例: [3, 3, 2] など)
    return list(set(itertools.permutations(factors)))

def build_dfmm_forest(targets_config):
    """
    DFMMアルゴリズムに基づき、各ターゲットの混合ツリー構造（親子関係）を構築します。
    複数のターゲットのツリーをまとめて「森 (forest)」として扱います。

    Args:
        targets_config (list[dict]): 各ターゲットの設定（'ratios', 'factors'を含む）のリスト。

    Returns:
        list[dict]: 各ツリーのノードと親子関係を格納した辞書のリスト（フォレスト）。
    """
    forest_structure = []
    for target in targets_config:
        ratios, factors = target['ratios'], target['factors']
        num_levels = len(factors)

        tree_nodes = {}
        # 最初は最下層（leaf node）の入力として試薬の比率を扱う
        values_to_process = list(ratios)
        nodes_from_below_ids = []

        # 混合ツリーを下のレベル（leaf）から上のレベル（root）へと構築していく
        for l in range(num_levels - 1, -1, -1):
            factor = factors[l]
            # 現在のレベルでの混合操作における「余り」と「商」を計算
            level_remainders = [v % factor for v in values_to_process]
            level_quotients = [v // factor for v in values_to_process]

            # 現在のレベルで必要となるノード（ミキサー）の数を計算
            # 入力は、試薬の余りと下位レベルから上がってきた中間液の合計
            total_inputs = sum(level_remainders) + len(nodes_from_below_ids)
            num_nodes_at_level = math.ceil(total_inputs / factor) if total_inputs > 0 else 0
            current_level_node_ids = [(l, k) for k in range(num_nodes_at_level)]

            # ノードをツリーに追加
            for node_id in current_level_node_ids:
                tree_nodes[node_id] = {'children': []}

            # 下のレベルからのノード（子）を、現在のレベルのノード（親）に均等に接続
            if num_nodes_at_level > 0:
                parent_idx = 0
                for child_id in nodes_from_below_ids:
                    parent_node_id = current_level_node_ids[parent_idx]
                    tree_nodes[parent_node_id]['children'].append(child_id)
                    parent_idx = (parent_idx + 1) % num_nodes_at_level # ラウンドロビンで割り当て

            # 次の（一つ上の）レベルの計算準備
            nodes_from_below_ids = current_level_node_ids
            values_to_process = level_quotients

        forest_structure.append(tree_nodes)
    return forest_structure

def calculate_p_values_from_structure(forest_structure, targets_config):
    """
    構築されたツリー構造に基づき、各ノードの「P値」を再帰的に計算します。
    P値は、そのノードが担当する混合液の相対的な「単位量」を表し、濃度計算の制約に不可欠です。

    Args:
        forest_structure (list[dict]): build_dfmm_forestで構築されたフォレスト。
        targets_config (list[dict]): 各ターゲットの設定リスト。

    Returns:
        list[dict]: 各ツリーのノードとそのP値を格納した辞書のリスト。
    """
    p_forest = []
    for m, tree_structure in enumerate(forest_structure):
        factors, memo, p_tree = targets_config[m]['factors'], {}, {}

        def prod(iterable):
            """イテラブルなオブジェクトの要素の積を計算するヘルパー関数。"""
            return reduce(operator.mul, iterable, 1)

        def get_p_for_node(node_id):
            """メモ化再帰を用いて、特定のノードのP値を計算する。"""
            if node_id in memo: return memo[node_id]
            level, k = node_id
            children = tree_structure.get(node_id, {}).get('children', [])

            if not children:
                # 子がいない場合（最下層に近いノード）、P値はそのレベル以降のfactorの積
                p = prod(factors[level:])
            else:
                # 子がいる場合、P値は子のP値の最大値にそのレベルのfactorを掛けたもの
                max_child_p = max(get_p_for_node(child_id) for child_id in children)
                p = max_child_p * factors[level]

            memo[node_id] = p
            return p

        # ツリー内の全ノードに対してP値を計算
        for node_id in tree_structure:
            p_tree[node_id] = get_p_for_node(node_id)
        p_forest.append(p_tree)
    return p_forest