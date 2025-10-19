# z3_solver.py
from reporting.reporter import SolutionReporter
import z3
import time
from config import MAX_SHARING_VOLUME

# --- ヘルパー関数群 ---
# これらの関数はクラス外で定義され、特定の計算をカプセル化します。

def _iterate_all_nodes(problem):
    """問題定義内の全てのノードを巡回するジェネレータ。"""
    for m, tree in enumerate(problem.forest):
        for l, nodes in tree.items():
            for k, node in enumerate(nodes):
                yield m, l, k, node

def _get_node_inputs(node):
    """特定のノードへの全入力（試薬、内部共有、外部共有）の変数をリストで返す。"""
    return (node.get('reagent_vars', []) +
            list(node.get('intra_sharing_vars', {}).values()) +
            list(node.get('inter_sharing_vars', {}).values()))

def _get_outgoing_vars(problem, m_src, l_src, k_src):
    """特定のノードから出ていく全ての共有液の変数をリストで返す。"""
    outgoing = []
    key_intra = f"from_l{l_src}k{k_src}"
    key_inter = f"from_m{m_src}_l{l_src}k{k_src}"
    # 全てのノードを宛先としてチェック
    for m_dst, tree_dst in enumerate(problem.forest):
        for l_dst, level_dst in tree_dst.items():
            for k_dst, node_dst in enumerate(level_dst):
                # 宛先ノードの共有変数辞書に、供給元としてのキーが存在するかチェック
                if m_src == m_dst and key_intra in node_dst.get('intra_sharing_vars', {}):
                    outgoing.append(node_dst['intra_sharing_vars'][key_intra])
                elif m_src != m_dst and key_inter in node_dst.get('inter_sharing_vars', {}):
                    outgoing.append(node_dst['inter_sharing_vars'][key_inter])
    return outgoing

# --- メインクラス ---
class Z3Solver:
    """
    Z3 SMTソルバーと対話し、最適化問題の制約を設定し、解を求める責務を持つクラス。
    """
    def __init__(self, problem, objective_mode="waste"):
        """
        コンストラクタ。

        Args:
            problem (MTWMProblem): 最適化問題の構造と変数を定義したオブジェクト。
            objective_mode (str): 最適化の目的 ('waste' or 'operations')。
        """
        self.problem = problem
        self.objective_mode = objective_mode
        self.opt = z3.Optimize() # Z3のOptimizeインスタンスを作成
        z3.set_param('memory_max_size', 8192) # Z3が使用する最大メモリを設定（MB）
        self.last_check_result = None
        self._set_all_constraints() # 全ての制約を設定
        self.objective_variable = self._set_objective_function() # 目的関数を設定

    def solve(self, checkpoint_handler):
        """
        最適化問題を解くメインのメソッド。
        より良い解を繰り返し探し、中断された場合は最良の解を返す。

        Args:
            checkpoint_handler (CheckpointHandler or None): チェックポイント管理オブジェクト。

        Returns:
            tuple: (best_model, best_value, best_analysis, elapsed_time)
        """
        last_best_value = None
        last_analysis = None
        # チェックポイントハンドラが存在する場合、前回の状態を読み込む
        if checkpoint_handler:
            last_best_value, last_analysis = checkpoint_handler.load_checkpoint()

        # 前回の最良値が存在すれば、それより良い解を探す制約を追加
        if last_best_value is not None:
            self.opt.add(self.objective_variable < last_best_value)

        print(f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) ---")
        print("(press Ctrl+C to interrupt and save)")

        best_model = None
        best_value = last_best_value
        best_analysis = last_analysis
        start_time = time.time()

        try:
            # z3.sat (解が存在する) が返される限りループ
            while self.check() == z3.sat:
                current_model = self.get_model()
                current_value = current_model.eval(self.objective_variable).as_long()
                print(f"Found a new, better solution with {self.objective_mode}: {current_value}")

                # 最良解を更新
                best_value = current_value
                best_model = current_model

                # チェックポイントハンドラが存在する場合、分析と保存を行う
                if checkpoint_handler:
                    reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
                    analysis = reporter.analyze_solution()
                    best_analysis = analysis
                    checkpoint_handler.save_checkpoint(analysis, best_value, time.time() - start_time)

                # 目的値が0になったら、それが最適解なのでループを抜ける
                if best_value == 0:
                    print(f"Found optimal solution with zero {self.objective_mode}.")
                    break

                # 次の探索では、今見つかった値よりもさらに小さい値を探す制約を追加
                self.opt.add(self.objective_variable < best_value)

        except KeyboardInterrupt:
            # ユーザーによる中断 (Ctrl+C)
            print("\nOptimization interrupted by user. Reporting the best solution found so far.")

        elapsed_time = time.time() - start_time
        print("--- Z3 Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time

    def check(self):
        """ソルバーに現在の制約下で解が存在するか問い合わせる。"""
        self.last_check_result = self.opt.check()
        return self.last_check_result

    def get_model(self):
        """check()がsatを返した場合に、解（モデル）を取得する。"""
        return self.opt.model()

    # --- 制約設定メソッド群 ---
    def _set_all_constraints(self):
        """全ての制約を設定するためのラッパーメソッド。"""
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_range_constraints()
        self._set_symmetry_breaking_constraints()
        self._set_activity_constraints()

    def _set_initial_constraints(self):
        """ルートノードの比率は、ターゲットの比率と一致しなければならない。"""
        for m, target in enumerate(self.problem.targets_config):
            root = self.problem.forest[m][0][0]
            for t in range(self.problem.num_reagents):
                self.opt.add(root['ratio_vars'][t] == target['ratios'][t])

    def _set_conservation_constraints(self):
        """流量保存則：各ノードから出ていく液体の総量は、そのノードで生成された総量以下でなければならない。"""
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            total_produced = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            self.opt.add(total_used <= total_produced)

    def _set_concentration_constraints(self):
        """濃度保存則：混合後のノードの各試薬の量は、混合前の各入力に含まれる試薬の量の合計と一致しなければならない。"""
        for m_dst, l_dst, k_dst, node in _iterate_all_nodes(self.problem):
            p_dst = self.problem.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            for t in range(self.problem.num_reagents):
                lhs = f_dst * node['ratio_vars'][t] # 左辺: 混合後の試薬量
                rhs_terms = [p_dst * node['reagent_vars'][t]] # 右辺: 混合前の試薬量の合計
                # 内部共有からの入力
                for key, w_var in node.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src = self.problem.forest[m_dst][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_dst][(l_src, k_src)]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                # 外部共有からの入力
                for key, w_var in node.get('inter_sharing_vars', {}).items():
                    m_src_str, lk_src_str = key.replace("from_m", "").split("_l")
                    m_src = int(m_src_str)
                    l_src, k_src = map(int, lk_src_str.split("k"))
                    r_src = self.problem.forest[m_src][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_src][(l_src, k_src)]
                    rhs_terms.append(r_src * w_var * (p_dst // p_src))
                self.opt.add(lhs == z3.Sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """各ノードにおける全試薬の比率の合計は、そのノードのP値と一致しなければならない。"""
        for m, target in enumerate(self.problem.targets_config):
            p_root = self.problem.p_values[m][(0, 0)]
            if sum(target['ratios']) != p_root:
                raise ValueError(
                    f"Target '{target['name']}' ratios sum ({sum(target['ratios'])}) "
                    f"does not match the root p-value ({p_root}). "
                    f"The sum of ratios must equal the product of all factors based on the generated tree."
                )
        for m, l, k, node in _iterate_all_nodes(self.problem):
            p_node = self.problem.p_values[m][(l, k)]
            self.opt.add(z3.Sum(node['ratio_vars']) == p_node)

    def _set_leaf_node_constraints(self):
        """最下層のノード（P値=F値）では、比率は直接投入される試薬量と等しい。"""
        for m, l, k, node in _iterate_all_nodes(self.problem):
            p_node = self.problem.p_values[m][(l, k)]
            f_node = self.problem.targets_config[m]['factors'][l]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.opt.add(node['ratio_vars'][t] == node['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        """各ミキサー（ノード）の総入力は0、またはそのレベルのFactor値と等しくなければならない。"""
        for m, l, k, node in _iterate_all_nodes(self.problem):
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum = z3.Sum(_get_node_inputs(node))
            if l == 0: # ルートノードは必ずFactor値と等しい
                self.opt.add(total_sum == f_value)
            else: # 他のノードは活動していればFactor値と等しい
                self.opt.add(z3.Implies(total_sum > 0, total_sum == f_value))
                self.opt.add(z3.Or(total_sum == 0, total_sum == f_value))

    def _set_range_constraints(self):
        """各変数（試薬量、共有量）は0以上、かつ物理的な上限値以下でなければならない。"""
        for m, l, k, node in _iterate_all_nodes(self.problem):
            upper_bound = self.problem.targets_config[m]['factors'][l] - 1
            for var in node.get('reagent_vars', []):
                self.opt.add(var >= 0, var <= upper_bound)
            sharing_vars = (list(node.get('intra_sharing_vars', {}).values()) +
                            list(node.get('inter_sharing_vars', {}).values()))
            for var in sharing_vars:
                effective_upper = upper_bound
                if MAX_SHARING_VOLUME is not None:
                    effective_upper = min(upper_bound, MAX_SHARING_VOLUME)
                self.opt.add(var >= 0, var <= effective_upper)

    def _set_symmetry_breaking_constraints(self):
        """解の対称性を破壊する制約。同じレベルのノードの活動量に順序を付け、探索空間を削減する。"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                if len(nodes) > 1:
                    for k in range(len(nodes) - 1):
                        total_input_k = z3.Sum(_get_node_inputs(nodes[k]))
                        total_input_k1 = z3.Sum(_get_node_inputs(nodes[k+1]))
                        self.opt.add(total_input_k >= total_input_k1)

    def _set_activity_constraints(self):
        """中間ノードが液体を生成した場合、その液体は必ずどこかで使用されなければならない。"""
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            if l_src == 0: continue # ルートノードは除く
            total_prod = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            self.opt.add(z3.Implies(total_prod > 0, total_used > 0))

    # z3_solver.py

    def _set_objective_function(self):
        """最適化の目的となる変数（総廃棄物量 or 総操作回数）を定義する。"""
        # --- 廃棄物量の定義 ---
        all_waste_vars = []
        for m_src, l_src, k_src, node in _iterate_all_nodes(self.problem):
            # 変更点: l_src == 0 は最終生成物（ルートノード）なので、廃棄物の計算から除外する
            if l_src == 0: continue
            total_prod = z3.Sum(_get_node_inputs(node))
            total_used = z3.Sum(_get_outgoing_vars(self.problem, m_src, l_src, k_src))
            waste_var = z3.Int(f"waste_m{m_src}_l{l_src}_k{k_src}")
            node['waste_var'] = waste_var # 後で参照できるようにノードに保存
            self.opt.add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
        total_waste = z3.Int("total_waste")
        self.opt.add(total_waste == z3.Sum(all_waste_vars))

        # --- 操作回数の定義 ---
        all_activity_vars = []
        for m, l, k, node in _iterate_all_nodes(self.problem):
            is_active = z3.Bool(f"active_m{m}_l{l}_k{k}")
            total_input = z3.Sum(_get_node_inputs(node))
            self.opt.add(is_active == (total_input > 0))
            all_activity_vars.append(z3.If(is_active, 1, 0))
        total_operations = z3.Int("total_operations")
        self.opt.add(total_operations == z3.Sum(all_activity_vars))

        # --- 総試薬使用量の定義 ---
        all_reagent_vars = []
        for _, _, _, node in _iterate_all_nodes(self.problem):
            all_reagent_vars.extend(node.get('reagent_vars', []))
        total_reagents = z3.Int("total_reagents")
        self.opt.add(total_reagents == z3.Sum(all_reagent_vars))

        # --- 最適化モードに応じて目的関数を設定 ---
        if self.objective_mode == 'waste':
            self.opt.minimize(total_waste) # 総廃棄物量を最小化
            return total_waste
        elif self.objective_mode == 'operations':
            self.opt.minimize(total_operations) # 総操作回数を最小化
            return total_operations
        elif self.objective_mode == 'reagents':
            self.opt.minimize(total_reagents) # 総試薬使用量を最小化
            return total_reagents
        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'. Must be 'waste', 'operations', or 'reagents'.")