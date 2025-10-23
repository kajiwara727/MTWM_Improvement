# or_tools_solver.py (最終修正版)
import time
from ortools.sat.python import cp_model
from reporting.reporter import SolutionReporter
from config import MAX_SHARING_VOLUME, MAX_MIXER_SIZE, MAX_LEVEL_DIFF
import sys
import z3 # SolutionReporter互換のために必要

# 再帰制限の引き上げ（必要に応じて）
sys.setrecursionlimit(2000)

# R * W * C 項の最大値。変数の最大値 (900) * 定数 (例: 5) でも 4500 程度。
# 安全性を考慮して大きめの値を設定します。
MAX_PRODUCT_BOUND = 50000 

# --- Or-Toolsへのデータアクセスアダプタ ---
class OrToolsModelAdapter:
    """Z3のModelRefの最小限のインターフェースを模倣し、Or-Toolsの値を返すアダプタ。
    SolutionReporterクラスを流用するために必要。
    """
    def __init__(self, solver, problem, forest_vars, objective_mode, objective_variable):
        self.solver = solver
        self.problem = problem
        self.forest_vars = forest_vars
        self.objective_mode = objective_mode
        self.objective_variable = objective_variable

    def _get_input_vars(self, node):
        """ノードへの全入力（試薬、内部共有、外部共有）のZ3変数オブジェクトをリストで返す。"""
        return (node.get('reagent_vars', []) +
                list(node.get('intra_sharing_vars', {}).values()) +
                list(node.get('inter_sharing_vars', {}).values()))

    def eval(self, z3_var):
        """Z3の変数（またはZ3のIntExpr）を受け取り、Or-Toolsの解の値を取得する。"""
        # 1. 目的変数の評価（total_waste や total_operations, total_reagents）
        if hasattr(z3_var, 'sexpr') and any(name in z3_var.sexpr() for name in ['total_waste', 'total_operations', 'total_reagents']):
             return self._get_value_wrapper(self.solver.ObjectiveValue())

        # 2. Z3の Sum(inputs) 式の評価 (Reporter.analyze_solution()で使用)
        # 渡された z3_var の子要素のセットと、各ノードの入力変数のセットを比較する
        
        # z3_var が複合式かどうかを判定 (子要素を持つ)
        if hasattr(z3_var, 'children') and z3_var.num_args() > 0:
            try:
                # 渡された Z3 Sum式の構成要素 (子要素) の名前のセットを取得
                z3_children_names = set(str(c) for c in z3_var.children())
            except:
                z3_children_names = set() # 取得できない場合はスキップ

            # 全てのノードを巡回し、Z3 Sum式の構成要素がどのノードの入力変数と一致するかを確認
            for m, tree_vars in enumerate(self.forest_vars):
                for l, level_vars in tree_vars.items():
                    for k, node_vars in enumerate(level_vars):
                        z3_node = self.problem.forest[m][l][k]
                        
                        # このノードの入力として定義されているZ3変数の名前のセットを取得
                        z3_node_inputs = self._get_input_vars(z3_node)
                        z3_node_input_names = set(str(v) for v in z3_node_inputs)

                        # Z3のSum式の構成要素とノードの入力変数のセットが完全に一致する場合
                        if z3_children_names == z3_node_input_names:
                            # Or-Toolsで事前に計算された total_input_var の値を返す
                            return self._get_value_wrapper(self.solver.Value(node_vars['total_input_var']))

        # 3. 個々の変数（比率、試薬、共有量、廃棄物）の評価 (z3_var is z3_node['...'])
        for m, tree_vars in enumerate(self.forest_vars):
            for l, level_vars in tree_vars.items():
                for k, node_vars in enumerate(level_vars):
                    z3_node = self.problem.forest[m][l][k]
                    
                    # 比率変数/試薬変数
                    for t in range(self.problem.num_reagents):
                        if z3_var is z3_node['ratio_vars'][t]:
                            return self._get_value_wrapper(self.solver.Value(node_vars['ratio_vars'][t]))
                        if z3_var is z3_node['reagent_vars'][t]:
                            return self._get_value_wrapper(self.solver.Value(node_vars['reagent_vars'][t]))
                            
                    # 共有変数
                    for z3_w_var, or_w_var in zip(z3_node.get('intra_sharing_vars', {}).values(), node_vars['intra_sharing_vars'].values()):
                        if z3_var is z3_w_var:
                             return self._get_value_wrapper(self.solver.Value(or_w_var))
                    for z3_w_var, or_w_var in zip(z3_node.get('inter_sharing_vars', {}).values(), node_vars['inter_sharing_vars'].values()):
                        if z3_var is z3_w_var:
                             return self._get_value_wrapper(self.solver.Value(or_w_var))

                    # 廃棄物変数
                    if 'waste_var' in z3_node and z3_var is z3_node['waste_var']:
                        return self._get_value_wrapper(self.solver.Value(node_vars['waste_var']))

        raise ValueError(f"Could not find Or-Tools variable corresponding to Z3 variable: {z3_var}")

    def _get_value_wrapper(self, value):
        """SolutionReporterが要求する as_long() メソッドを持つラッパーオブジェクトを返す。"""
        class OrToolsValue:
            def __init__(self, val): self.value = val
            def as_long(self): return int(value)
        # valueがNoneの場合は0を返す (Or-Toolsが値を設定しなかった場合)
        return OrToolsValue(value if value is not None else 0)
        
    def get_model(self):
        # SolutionReporterの互換性のために、evalメソッドを持つ自身を返す
        return self
        
class OrToolsSolver:
    """
    Or-Tools CP-SATソルバーと対話し、最適化問題の制約を設定し、解を求めるクラス。
    """
    def __init__(self, problem, objective_mode="waste"):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        
        # Z3の solve() との互換性のために必要な変数定義と制約設定
        self.forest_vars = []
        self._set_variables_and_constraints()

    def solve(self, checkpoint_handler):
        """最適化問題を解くメインのメソッド（Or-Tools CP-SAT版）。"""
        
        # Z3のIncremental Solvingループは不要。Minimize()とSolve()で最適解を直接探索する。
        # チェックポイント機能は、Z3のsolve()のロジックを簡略化して実現。
        last_best_value = None
        last_analysis = None
        
        if checkpoint_handler:
            last_best_value, last_analysis = checkpoint_handler.load_checkpoint()

        start_time = time.time()
        
        # 前回の最良値が存在すれば、それより良い解を探す制約を追加
        if last_best_value is not None:
             # 前回の最良値よりも小さい値を目的変数に制約
             self.model.Add(self.objective_variable < int(last_best_value))

        print(f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")

        # ソルバーの実行
        status = self.solver.Solve(self.model)
        elapsed_time = time.time() - start_time
        
        best_model = None
        best_value = None
        best_analysis = None
        
        # Or-ToolsのSolve()は、最適解が見つかった場合に cp_model.OPTIMAL を返す
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            print(f"Or-Tools found an optimal solution with {self.objective_mode}: {int(best_value)}")

            # SolutionReporter互換のためのアダプタを生成
            best_model = OrToolsModelAdapter(self.solver, self.problem, self.forest_vars, self.objective_mode, self.objective_variable)
            
            # SolutionReporterによる分析
            reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
            best_analysis = reporter.analyze_solution()
            
            # チェックポイント保存 (CP-SATは一発で最適解を見つけるが、中間結果を保存するロジックを模倣)
            if checkpoint_handler:
                 # CheckpointHandlerに渡す値はint()に変換
                 checkpoint_handler.save_checkpoint(best_analysis, int(best_value), elapsed_time)

        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
            if last_best_value is not None and status == cp_model.INFEASIBLE:
                 print("Did not find a better solution than the checkpoint. Reporting checkpoint solution.")
                 best_value = last_best_value
                 best_analysis = last_analysis
                 # チェックポイントからレポート生成
                 reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
                 reporter.report_from_checkpoint(last_analysis, last_best_value, "") # output_dir は空文字
            elif status == cp_model.INFEASIBLE:
                print("No feasible solution found.")

        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time

    # --- 変数定義と制約設定メソッド群 ---
    def _set_variables_and_constraints(self):
        """全ての変数定義と制約設定を統括する。"""
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints() # <-- ここが修正の中心
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_range_constraints()
        self._set_activity_constraints()
        self.objective_variable = self._set_objective_function()
        
    def _define_or_tools_variables(self):
        """MTWMProblemの構造を借用し、Or-Toolsの変数を定義する。"""
        # 変数の最大値は、Ratio Sumの最大値 * Max Mixer Size * 共有上限値で大まかに見積もる
        max_ratio_sum = max(sum(t['ratios']) for t in self.problem.targets_config) if self.problem.targets_config else 1
        # MAX_BOUND は元のZ3Solverの変数範囲（整数）と一致させるために、
        # 経験的にZ3の問題設定に近い 900 程度を使用
        MAX_BOUND = max_ratio_sum * (MAX_MIXER_SIZE or 1) * 10
        if MAX_BOUND < 900: MAX_BOUND = 900
        
        for m, z3_tree in enumerate(self.problem.forest):
            tree_data = {}
            for l, z3_nodes in z3_tree.items():
                level_nodes = []
                for k, z3_node in enumerate(z3_nodes):
                    # 各ノードに必要なOr-Tools変数を定義
                    node_vars = {
                        # 比率変数
                        'ratio_vars': [self.model.NewIntVar(0, MAX_BOUND, f"R_m{m}_l{l}_k{k}_t{t}") for t in range(self.problem.num_reagents)],
                        # 試薬変数
                        'reagent_vars': [self.model.NewIntVar(0, MAX_BOUND, f"r_m{m}_l{l}_k{k}_t{t}") for t in range(self.problem.num_reagents)],
                        'intra_sharing_vars': {},
                        'inter_sharing_vars': {},
                        # 総入力、活動状態、廃棄物量を表すヘルパー変数
                        'total_input_var': self.model.NewIntVar(0, MAX_BOUND, f"TotalInput_m{m}_l{l}_k{k}"),
                        'is_active_var': self.model.NewBoolVar(f"IsActive_m{m}_l{l}_k{k}"),
                        'waste_var': self.model.NewIntVar(0, MAX_BOUND, f"waste_m{m}_l{l}_k{k}")
                    }
                    # 共有変数を定義 (Z3変数のキーと名前を流用)
                    # 共有液量の上限は MAX_BOUND と MAX_SHARING_VOLUME の小さい方
                    max_sharing_vol = min(MAX_BOUND, MAX_SHARING_VOLUME or MAX_BOUND)
                    
                    for key in z3_node.get('intra_sharing_vars', {}).keys():
                         node_vars['intra_sharing_vars'][key] = self.model.NewIntVar(0, max_sharing_vol, f"w_intra_{m}_{l}_{k}_{key}")
                    for key in z3_node.get('inter_sharing_vars', {}).keys():
                         node_vars['inter_sharing_vars'][key] = self.model.NewIntVar(0, max_sharing_vol, f"w_inter_{m}_{l}_{k}_{key}")
                        
                    level_nodes.append(node_vars)
                tree_data[l] = level_nodes
            self.forest_vars.append(tree_data)

    # Z3のヘルパー関数と同様のロジックでOr-Toolsの変数を取得するメソッド
    def _get_input_vars(self, node_vars):
        return (node_vars.get('reagent_vars', []) +
                list(node_vars.get('intra_sharing_vars', {}).values()) +
                list(node_vars.get('inter_sharing_vars', {}).values()))

    def _get_outgoing_vars(self, m_src, l_src, k_src):
        outgoing = []
        key_intra = f"from_l{l_src}k{k_src}"
        key_inter = f"from_m{m_src}_l{l_src}k{k_src}"
        for m_dst, tree_dst in enumerate(self.forest_vars):
            for l_dst, level_dst in tree_dst.items():
                for k_dst, node_dst in enumerate(level_dst):
                    if m_src == m_dst and key_intra in node_dst.get('intra_sharing_vars', {}):
                        outgoing.append(node_dst['intra_sharing_vars'][key_intra])
                    elif m_src != m_dst and key_inter in node_dst.get('inter_sharing_vars', {}):
                        outgoing.append(node_dst['inter_sharing_vars'][key_inter])
        return outgoing
    
    def _iterate_all_nodes(self):
        for m, tree in enumerate(self.forest_vars):
            for l, nodes in tree.items():
                for k, node in enumerate(nodes):
                    yield m, l, k, node

    # --- 制約設定メソッド (Z3からOr-Tools構文への書き換え) ---
    def _set_initial_constraints(self):
        """ルートノードの比率がターゲット比率と一致する。"""
        for m, target in enumerate(self.problem.targets_config):
            root_vars = self.forest_vars[m][0][0]
            for t in range(self.problem.num_reagents):
                self.model.Add(root_vars['ratio_vars'][t] == target['ratios'][t])

    def _set_conservation_constraints(self):
        """流量保存則。総生産量 == 総入力。"""
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            total_produced = node_vars['total_input_var']
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))
            # Z3の <= 制約は、廃棄物変数と組み合わせて _set_objective_function で再定義される。

    def _set_concentration_constraints(self):
        """濃度保存則。線形制約として記述。（非線形項を線形化）"""
        for m_dst, l_dst, k_dst, node_vars in self._iterate_all_nodes():
            p_dst = self.problem.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            
            for t in range(self.problem.num_reagents):
                lhs = f_dst * node_vars['ratio_vars'][t]
                rhs_terms = [p_dst * node_vars['reagent_vars'][t]]
                
                # 内部共有
                for key, w_var in node_vars.get('intra_sharing_vars', {}).items():
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src = self.forest_vars[m_dst][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_dst][(l_src, k_src)]
                    
                    # 非線形項 (r_src * w_var) の線形化
                    product_var = self.model.NewIntVar(0, MAX_PRODUCT_BOUND, f"Prod_intra_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}")
                    self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
                    
                    scale_factor = (p_dst // p_src)
                    rhs_terms.append(product_var * scale_factor) 
                    
                # 外部共有
                for key, w_var in node_vars.get('inter_sharing_vars', {}).items():
                    m_src_str, lk_src_str = key.replace("from_m", "").split("_l")
                    m_src = int(m_src_str)
                    l_src, k_src = map(int, lk_src_str.split("k"))
                    r_src = self.forest_vars[m_src][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_src][(l_src, k_src)]

                    # 非線形項 (r_src * w_var) の線形化
                    product_var = self.model.NewIntVar(0, MAX_PRODUCT_BOUND, f"Prod_inter_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}")
                    self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
                    
                    scale_factor = (p_dst // p_src)
                    rhs_terms.append(product_var * scale_factor)
                
                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """各ノードの比率の合計がP値と一致する。"""
        for m, l, k, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            self.model.Add(sum(node_vars['ratio_vars']) == p_node)

    def _set_leaf_node_constraints(self):
        """最下層ノードでは、比率 == 試薬投入量。"""
        for m, l, k, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            f_node = self.problem.targets_config[m]['factors'][l]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.model.Add(node_vars['ratio_vars'][t] == node_vars['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        """ミキサーの活動制約: 総入力が0またはFactor値と等しい。"""
        for m, l, k, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum = node_vars['total_input_var']
            is_active = node_vars['is_active_var']
            
            if l == 0: # ルートノードは必ずFactor値と等しい
                self.model.Add(total_sum == f_value)
            else: # 他のノードは活動していればFactor値と等しい (Reified Constraint)
                # is_active == True なら total_sum == f_value
                self.model.Add(total_sum == f_value).OnlyEnforceIf(is_active)
                # is_active == False なら total_sum == 0
                self.model.Add(total_sum == 0).OnlyEnforceIf(is_active.Not())

    def _set_range_constraints(self):
        """各変数（試薬量、共有量）は0以上、かつ物理的な上限値以下。"""
        # 0以上の制約はNewIntVarで定義済み。ここでは上限制約のみ。
        for m, l, k, node_vars in self._iterate_all_nodes():
            # 試薬変数の上限は factor - 1
            upper_bound = self.problem.targets_config[m]['factors'][l] - 1
            
            for var in node_vars.get('reagent_vars', []):
                self.model.Add(var <= upper_bound)
            
            sharing_vars = (list(node_vars.get('intra_sharing_vars', {}).values()) +
                            list(node_vars.get('inter_sharing_vars', {}).values()))
            
            effective_upper = upper_bound
            if MAX_SHARING_VOLUME is not None:
                effective_upper = min(upper_bound, MAX_SHARING_VOLUME)

            for var in sharing_vars:
                # 共有変数の上限は NewIntVar の定義時に設定済み（_define_or_tools_variablesを参照）
                # ここではチェックのみ
                pass
                
    def _set_activity_constraints(self):
        """中間ノードが液体を生成した場合、その液体は必ずどこかで使用されなければならない。"""
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            if l_src == 0: continue # ルートノードは除く
            
            total_prod = node_vars['total_input_var']
            total_used = sum(self._get_outgoing_vars(m_src, l_src, k_src))
            is_active = node_vars['is_active_var'] # total_prod > 0 の時 True
            
            # total_used > 0 <=> is_used
            is_used = self.model.NewBoolVar(f"IsUsed_m{m_src}_l{l_src}_k{k_src}")
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_used)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_used.Not())
            
            # Implies (is_active => is_used)
            self.model.AddImplication(is_active, is_used)

    def _set_objective_function(self):
        """目的変数を定義し、最小化を設定する。"""
        all_waste_vars = []
        
        # We need to iterate over the *problem's* forest as well to inject the z3 variable
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            
            # --- Get the original Z3 node structure for compatibility ---
            z3_node = self.problem.forest[m_src][l_src][k_src]
            
            if l_src == 0: continue 

            total_prod = node_vars['total_input_var']
            total_used = sum(self._get_outgoing_vars(m_src, l_src, k_src))
            
            # waste_var == total_prod - total_used
            waste_var = node_vars['waste_var']
            self.model.Add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            
            # --- FIX: Inject Z3 placeholder variable into problem structure ---
            # SolutionReporter expects to find a Z3 variable object in z3_node['waste_var']
            # We must create this object and store it here to maintain compatibility.
            if 'waste_var' not in z3_node:
                 z3_dummy_waste_var = z3.Int(f"waste_m{m_src}_l{l_src}_k{k_src}")
                 z3_node['waste_var'] = z3_dummy_waste_var

        total_waste = sum(all_waste_vars)
        
        # --- 操作回数の定義 ---
        all_activity_vars = [node_vars['is_active_var'] for m, l, k, node_vars in self._iterate_all_nodes()]
        total_operations = sum(all_activity_vars)

        # --- 総試薬使用量の定義 (新要素) ---
        all_reagent_vars = []
        for _, _, _, node_vars in self._iterate_all_nodes():
            all_reagent_vars.extend(node_vars.get('reagent_vars', []))
        total_reagents = sum(all_reagent_vars) # LinearExprとして使用

        # --- 最適化モードに応じて目的関数を設定 ---
        if self.objective_mode == 'waste':
            self.model.Minimize(total_waste)
            return total_waste
        elif self.objective_mode == 'operations':
            self.model.Minimize(total_operations)
            return total_operations
        elif self.objective_mode == 'reagents': # 'reagents' モードを追加
            self.model.Minimize(total_reagents)
            return total_reagents
        else:
            # エラーメッセージを更新
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'. Must be 'waste', 'operations', or 'reagents'.")