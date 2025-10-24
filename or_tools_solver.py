# or_tools_solver.py (最終修正版 + Rノード対応 v2)
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
    def __init__(self, solver_instance, problem, forest_vars, peer_vars, objective_mode, objective_variable):
        self.solver = solver_instance.solver # cp_model.CpSolver
        self.problem = problem
        self.forest_vars = forest_vars
        self.peer_vars = peer_vars # <--- 追加
        self.objective_mode = objective_mode
        self.objective_variable = objective_variable

    def _get_input_vars(self, node):
        """ノードへの全入力（試薬、内部共有、外部共有）のZ3変数オブジェクトをリストで返す。"""
        # (SolutionReporterがDFMMノードに対してのみ呼び出すため、変更不要)
        return (node.get('reagent_vars', []) +
                list(node.get('intra_sharing_vars', {}).values()) +
                list(node.get('inter_sharing_vars', {}).values()))

    def eval(self, z3_var):
        """Z3の変数（またはZ3のIntExpr）を受け取り、Or-Toolsの解の値を取得する。"""
        # 1. 目的変数の評価（total_waste や total_operations, total_reagents）
        if hasattr(z3_var, 'sexpr') and any(name in z3_var.sexpr() for name in ['total_waste', 'total_operations', 'total_reagents']):
             return self._get_value_wrapper(self.solver.ObjectiveValue())

        # z3_var が複合式(Sum)かどうかを判定
        if hasattr(z3_var, 'children') and z3_var.num_args() > 0:
            try:
                z3_children_names = set(str(c) for c in z3_var.children())
            except:
                z3_children_names = set()

            # 2a. Z3の Sum(inputs) 式の評価 (DFMMノード)
            for m, tree_vars in enumerate(self.forest_vars):
                for l, level_vars in tree_vars.items():
                    for k, node_vars in enumerate(level_vars):
                        z3_node = self.problem.forest[m][l][k]
                        z3_node_inputs = self._get_input_vars(z3_node)
                        z3_node_input_names = set(str(v) for v in z3_node_inputs)
                        if z3_children_names == z3_node_input_names:
                            return self._get_value_wrapper(self.solver.Value(node_vars['total_input_var']))
            
            # 2b. Z3の Sum(inputs) 式の評価 (ピアRノード)
            for i, or_peer_node in enumerate(self.peer_vars):
                z3_peer_node = self.problem.peer_nodes[i]
                z3_node_inputs = list(z3_peer_node['input_vars'].values())
                z3_node_input_names = set(str(v) for v in z3_node_inputs)
                if z3_children_names == z3_node_input_names:
                    return self._get_value_wrapper(self.solver.Value(or_peer_node['total_input_var']))


        # 3a. 個々の変数（比率、試薬、共有量、廃棄物）の評価 (DFMMノード)
        for m, tree_vars in enumerate(self.forest_vars):
            for l, level_vars in tree_vars.items():
                for k, node_vars in enumerate(level_vars):
                    z3_node = self.problem.forest[m][l][k]
                    # (...既存の比率、試薬、共有、廃棄物変数のチェック...)
                    for t in range(self.problem.num_reagents):
                        if z3_var is z3_node['ratio_vars'][t]:
                            return self._get_value_wrapper(self.solver.Value(node_vars['ratio_vars'][t]))
                        if z3_var is z3_node['reagent_vars'][t]:
                            return self._get_value_wrapper(self.solver.Value(node_vars['reagent_vars'][t]))
                    for z3_w_var, or_w_var in zip(z3_node.get('intra_sharing_vars', {}).values(), node_vars['intra_sharing_vars'].values()):
                        if z3_var is z3_w_var:
                             return self._get_value_wrapper(self.solver.Value(or_w_var))
                    for z3_w_var, or_w_var in zip(z3_node.get('inter_sharing_vars', {}).values(), node_vars['inter_sharing_vars'].values()):
                        if z3_var is z3_w_var:
                             return self._get_value_wrapper(self.solver.Value(or_w_var))
                    if 'waste_var' in z3_node and z3_var is z3_node['waste_var']:
                        return self._get_value_wrapper(self.solver.Value(node_vars['waste_var']))

        # 3b. 個々の変数（比率、入力、廃棄物）の評価 (ピアRノード)
        for i, or_peer_node in enumerate(self.peer_vars):
            z3_peer_node = self.problem.peer_nodes[i]
            # 比率
            for t in range(self.problem.num_reagents):
                if z3_var is z3_peer_node['ratio_vars'][t]:
                    return self._get_value_wrapper(self.solver.Value(or_peer_node['ratio_vars'][t]))
            # 入力
            if z3_var is z3_peer_node['input_vars']['from_a']:
                return self._get_value_wrapper(self.solver.Value(or_peer_node['input_vars']['from_a']))
            if z3_var is z3_peer_node['input_vars']['from_b']:
                return self._get_value_wrapper(self.solver.Value(or_peer_node['input_vars']['from_b']))
            # 廃棄物
            if 'waste_var' in z3_peer_node and z3_var is z3_peer_node['waste_var']:
                return self._get_value_wrapper(self.solver.Value(or_peer_node['waste_var']))


        raise ValueError(f"Could not find Or-Tools variable corresponding to Z3 variable: {z3_var}")

    def _get_value_wrapper(self, value):
        """SolutionReporterが要求する as_long() メソッドを持つラッパーオブジェクトを返す。"""
        class OrToolsValue:
            def __init__(self, val): self.value = val
            def as_long(self): return int(value)
        return OrToolsValue(value if value is not None else 0)
        
    def get_model(self):
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
        
        self.forest_vars = []
        self.peer_vars = [] # <--- 追加
        self._set_variables_and_constraints()

    def solve(self, checkpoint_handler):
        """最適化問題を解くメインのメソッド（Or-Tools CP-SAT版）。"""
        
        last_best_value = None
        last_analysis = None
        
        if checkpoint_handler:
            last_best_value, last_analysis = checkpoint_handler.load_checkpoint()

        start_time = time.time()
        
        if last_best_value is not None:
             self.model.Add(self.objective_variable < int(last_best_value))

        print(f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")

        status = self.solver.Solve(self.model)
        elapsed_time = time.time() - start_time
        
        best_model = None
        best_value = None
        best_analysis = None
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            print(f"Or-Tools found an optimal solution with {self.objective_mode}: {int(best_value)}")

            # SolutionReporter互換のためのアダプタを生成 (self.peer_vars を渡す)
            best_model = OrToolsModelAdapter(self, self.problem, self.forest_vars, self.peer_vars, self.objective_mode, self.objective_variable)
            
            reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
            best_analysis = reporter.analyze_solution()
            
            if checkpoint_handler:
                 checkpoint_handler.save_checkpoint(best_analysis, int(best_value), elapsed_time)
        else:
            # (...既存のエラーハンドリング...)
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
            if last_best_value is not None and status == cp_model.INFEASIBLE:
                 print("Did not find a better solution than the checkpoint. Reporting checkpoint solution.")
                 best_value = last_best_value
                 best_analysis = last_analysis
                 reporter = SolutionReporter(self.problem, best_model, self.objective_mode)
                 reporter.report_from_checkpoint(last_analysis, last_best_value, "")
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
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_range_constraints()
        self._set_activity_constraints() # <--- 修正対象
        self._set_peer_mixing_constraints() 
        self.objective_variable = self._set_objective_function()
        
    def _define_or_tools_variables(self):
        """DFMMノードとピアRノードのOr-Tools変数を定義する。"""
        
        max_ratio_sum = max(sum(t['ratios']) for t in self.problem.targets_config) if self.problem.targets_config else 1
        MAX_BOUND = max_ratio_sum * (MAX_MIXER_SIZE or 1) * 10
        if MAX_BOUND < 900: MAX_BOUND = 900
        
        # 1. DFMMノードの変数を定義 (self.forest_vars)
        for m, z3_tree in enumerate(self.problem.forest):
            tree_data = {}
            for l, z3_nodes in z3_tree.items():
                level_nodes = []
                for k, z3_node in enumerate(z3_nodes):
                    # ( ... 既存の 'ratio_vars', 'reagent_vars', 'sharing_vars' ... )
                    node_vars = {
                        'ratio_vars': [self.model.NewIntVar(0, MAX_BOUND, f"R_m{m}_l{l}_k{k}_t{t}") for t in range(self.problem.num_reagents)],
                        'reagent_vars': [self.model.NewIntVar(0, MAX_BOUND, f"r_m{m}_l{l}_k{k}_t{t}") for t in range(self.problem.num_reagents)],
                        'intra_sharing_vars': {},
                        'inter_sharing_vars': {},
                        'total_input_var': self.model.NewIntVar(0, MAX_BOUND, f"TotalInput_m{m}_l{l}_k{k}"),
                        'is_active_var': self.model.NewBoolVar(f"IsActive_m{m}_l{l}_k{k}"),
                        'waste_var': self.model.NewIntVar(0, MAX_BOUND, f"waste_m{m}_l{l}_k{k}")
                    }
                    max_sharing_vol = min(MAX_BOUND, MAX_SHARING_VOLUME or MAX_BOUND)
                    for key in z3_node.get('intra_sharing_vars', {}).keys():
                         node_vars['intra_sharing_vars'][key] = self.model.NewIntVar(0, max_sharing_vol, f"w_intra_{m}_{l}_{k}_{key}")
                    for key in z3_node.get('inter_sharing_vars', {}).keys():
                         # 【変更】Rノードからの入力キーもここで定義される
                         # (例: key = "from_R_idx5")
                         node_vars['inter_sharing_vars'][key] = self.model.NewIntVar(0, max_sharing_vol, f"w_inter_{m}_{l}_{k}_{key}")
                        
                    level_nodes.append(node_vars)
                tree_data[l] = level_nodes
            self.forest_vars.append(tree_data)

        # 2. ピアRノードの変数を定義 (self.peer_vars)
        for i, z3_peer_node in enumerate(self.problem.peer_nodes):
            name = z3_peer_node['name']
            p_val = z3_peer_node['p_value']
            
            node_vars = {
                'name': name,
                'p_value': p_val,
                'source_a_id': z3_peer_node['source_a_id'],
                'source_b_id': z3_peer_node['source_b_id'],
                # このノードの比率 (0 <= r <= P)
                'ratio_vars': [self.model.NewIntVar(0, p_val, f"R_{name}_t{t}") for t in range(self.problem.num_reagents)],
                # このノードへの入力 (0 or 1)
                'input_vars': {
                    'from_a': self.model.NewIntVar(0, 1, f"w_peer_a_to_{name}"),
                    'from_b': self.model.NewIntVar(0, 1, f"w_peer_b_to_{name}")
                },
                # 総入力 (0 or 2)
                'total_input_var': self.model.NewIntVar(0, 2, f"TotalInput_{name}"),
                'is_active_var': self.model.NewBoolVar(f"IsActive_{name}"),
                'waste_var': self.model.NewIntVar(0, 2, f"waste_{name}") # ピア混合は最大2しか生産しない
            }
            self.peer_vars.append(node_vars)


    def _get_input_vars(self, node_vars):
        # (DFMMノード用ヘルパー、変更不要)
        return (node_vars.get('reagent_vars', []) +
                list(node_vars.get('intra_sharing_vars', {}).values()) +
                list(node_vars.get('inter_sharing_vars', {}).values()))

    def _get_outgoing_vars(self, m_src, l_src, k_src):
        """【変更】DFMMノード (m_src, l_src, k_src) からの総出力を取得。
           ピアRノードへの出力も含む。
        """
        outgoing = []
        key_intra = f"from_l{l_src}k{k_src}"
        key_inter = f"from_m{m_src}_l{l_src}k{k_src}"
        
        # 1. 宛先が DFMMノードの場合 (既存)
        for m_dst, tree_dst in enumerate(self.forest_vars):
            for l_dst, level_dst in tree_dst.items():
                for k_dst, node_dst in enumerate(level_dst):
                    if m_src == m_dst and key_intra in node_dst.get('intra_sharing_vars', {}):
                        outgoing.append(node_dst['intra_sharing_vars'][key_intra])
                    elif m_src != m_dst and key_inter in node_dst.get('inter_sharing_vars', {}):
                        outgoing.append(node_dst['inter_sharing_vars'][key_inter])
        
        # 2. 宛先が ピアRノードの場合 (新規)
        for or_peer_node in self.peer_vars:
            if (m_src, l_src, k_src) == or_peer_node['source_a_id']:
                outgoing.append(or_peer_node['input_vars']['from_a'])
            if (m_src, l_src, k_src) == or_peer_node['source_b_id']:
                outgoing.append(or_peer_node['input_vars']['from_b'])
                
        return outgoing
    
    def _get_outgoing_vars_from_peer(self, peer_node_index):
        """【新規】ピアRノード (index) からの総出力を取得。
           (宛先は常にDFMMノード)
        """
        outgoing = []
        key_inter = f"from_R_idx{peer_node_index}"
        
        for m_dst, tree_dst in enumerate(self.forest_vars):
            for l_dst, level_dst in tree_dst.items():
                for k_dst, node_dst in enumerate(level_dst):
                    if key_inter in node_dst.get('inter_sharing_vars', {}):
                        outgoing.append(node_dst['inter_sharing_vars'][key_inter])
        return outgoing
    
    def _iterate_all_nodes(self):
        # (DFMMノード用イテレータ、変更不要)
        for m, tree in enumerate(self.forest_vars):
            for l, nodes in tree.items():
                for k, node in enumerate(nodes):
                    yield m, l, k, node

    # --- 制約設定メソッド (Z3からOr-Tools構文への書き換え) ---
    def _set_initial_constraints(self):
        # (変更不要)
        for m, target in enumerate(self.problem.targets_config):
            root_vars = self.forest_vars[m][0][0]
            for t in range(self.problem.num_reagents):
                self.model.Add(root_vars['ratio_vars'][t] == target['ratios'][t])

    def _set_conservation_constraints(self):
        # (変更不要)
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            total_produced = node_vars['total_input_var']
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))

    def _set_concentration_constraints(self):
        """濃度保存則。(DFMMノード用)"""
        for m_dst, l_dst, k_dst, node_vars in self._iterate_all_nodes():
            p_dst = self.problem.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.problem.targets_config[m_dst]['factors'][l_dst]
            
            for t in range(self.problem.num_reagents):
                lhs = f_dst * node_vars['ratio_vars'][t]
                rhs_terms = [p_dst * node_vars['reagent_vars'][t]]
                
                # 内部共有
                for key, w_var in node_vars.get('intra_sharing_vars', {}).items():
                    # ( ... 既存の内部共有ロジック ... )
                    l_src, k_src = map(int, key.replace("from_l", "").split("k"))
                    r_src = self.forest_vars[m_dst][l_src][k_src]['ratio_vars'][t]
                    p_src = self.problem.p_values[m_dst][(l_src, k_src)]
                    product_var = self.model.NewIntVar(0, MAX_PRODUCT_BOUND, f"Prod_intra_m{m_dst}l{l_dst}k{k_dst}_t{t}_from_{key}")
                    self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
                    scale_factor = (p_dst // p_src)
                    rhs_terms.append(product_var * scale_factor) 
                    
                # 外部共有 (DFMMノード または Rノード から)
                for key, w_var in node_vars.get('inter_sharing_vars', {}).items():
                    
                    if key.startswith('from_R_idx'):
                        # 【新規】Rノードからの入力
                        r_node_idx = int(key.replace('from_R_idx', ''))
                        or_peer_node = self.peer_vars[r_node_idx]
                        r_src = or_peer_node['ratio_vars'][t]
                        p_src = or_peer_node['p_value']
                        
                    else:
                        # 【既存】DFMMノードからの入力
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
        # (DFMMノード用、変更不要)
        for m, l, k, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            self.model.Add(sum(node_vars['ratio_vars']) == p_node)

    def _set_leaf_node_constraints(self):
        # (DFMMノード用、変更不要)
        for m, l, k, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_values[m][(l, k)]
            f_node = self.problem.targets_config[m]['factors'][l]
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.model.Add(node_vars['ratio_vars'][t] == node_vars['reagent_vars'][t])

    def _set_mixer_capacity_constraints(self):
        # (DFMMノード用、変更不要)
        for m, l, k, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[m]['factors'][l]
            total_sum = node_vars['total_input_var']
            is_active = node_vars['is_active_var']
            if l == 0:
                self.model.Add(total_sum == f_value)
            else:
                self.model.Add(total_sum == f_value).OnlyEnforceIf(is_active)
                self.model.Add(total_sum == 0).OnlyEnforceIf(is_active.Not())

    def _set_range_constraints(self):
        # (DFMMノード用、変更不要)
        for m, l, k, node_vars in self._iterate_all_nodes():
            upper_bound = self.problem.targets_config[m]['factors'][l] - 1
            for var in node_vars.get('reagent_vars', []):
                self.model.Add(var <= upper_bound)
            # (共有変数の上限は _define_or_tools_variables で設定済み)

    def _set_activity_constraints(self):
        """
        【修正】中間ノードが液体を生成した場合、その液体は必ずどこかで使用されなければならない。
        DFMMノードとRノードの両方に適用する。
        """
        
        # 1. DFMMノード (ルートノードは除く)
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

        # 2. 【新規】ピアRノード
        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node['total_input_var'] # 0 or 2
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            is_active = or_peer_node['is_active_var'] # total_prod > 0 の時 True
            
            # total_used > 0 <=> is_used
            is_used = self.model.NewBoolVar(f"IsUsed_Peer_{i}")
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_used)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_used.Not())
            
            # Implies (is_active => is_used)
            self.model.AddImplication(is_active, is_used)


    def _set_peer_mixing_constraints(self):
        """【新規】ピアRノード専用の制約を設定する。"""
        for i, or_peer_node in enumerate(self.peer_vars):
            total_input = or_peer_node['total_input_var']
            is_active = or_peer_node['is_active_var']
            w_a = or_peer_node['input_vars']['from_a']
            w_b = or_peer_node['input_vars']['from_b']
            
            # 総入力の定義
            self.model.Add(total_input == w_a + w_b)
            
            # 1. 活動制約 (1:1 Mix, Size 2)
            # is_active == True -> total_input == 2, w_a == 1, w_b == 1
            self.model.Add(total_input == 2).OnlyEnforceIf(is_active)
            self.model.Add(w_a == 1).OnlyEnforceIf(is_active)
            self.model.Add(w_b == 1).OnlyEnforceIf(is_active)
            # is_active == False -> total_input == 0, w_a == 0, w_b == 0
            self.model.Add(total_input == 0).OnlyEnforceIf(is_active.Not())
            self.model.Add(w_a == 0).OnlyEnforceIf(is_active.Not())
            self.model.Add(w_b == 0).OnlyEnforceIf(is_active.Not())

            # 2. 比率の和の制約 (Constraint 4)
            p_val = or_peer_node['p_value']
            r_new_vars = or_peer_node['ratio_vars']
            # is_active == True -> Sum(r_new) == P
            self.model.Add(sum(r_new_vars) == p_val).OnlyEnforceIf(is_active)
            # is_active == False -> Sum(r_new) == 0
            self.model.Add(sum(r_new_vars) == 0).OnlyEnforceIf(is_active.Not())

            # 3. 濃度保存則 (Constraint 3: 2*r = r1+r2)
            m_a, l_a, k_a = or_peer_node['source_a_id']
            r_a_vars = self.forest_vars[m_a][l_a][k_a]['ratio_vars']
            m_b, l_b, k_b = or_peer_node['source_b_id']
            r_b_vars = self.forest_vars[m_b][l_b][k_b]['ratio_vars']

            for t in range(self.problem.num_reagents):
                lhs = 2 * r_new_vars[t]
                rhs = r_a_vars[t] + r_b_vars[t]
                # この制約は is_active の時のみ適用
                self.model.Add(lhs == rhs).OnlyEnforceIf(is_active)


    def _set_objective_function(self):
        """【変更】目的変数を定義する。DFMMノードとRノードの両方を集計。"""
        
        all_waste_vars = []
        all_activity_vars = []
        all_reagent_vars = [] # (試薬はDFMMノードのみ)

        # 1. DFMMノードの集計
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            z3_node = self.problem.forest[m_src][l_src][k_src]
            
            # 廃棄物
            if l_src != 0: # ルートノードは廃棄物計算から除外
                total_prod = node_vars['total_input_var']
                # _get_outgoing_vars は Rノードへの出力を自動的に含む (修正済み)
                total_used = sum(self._get_outgoing_vars(m_src, l_src, k_src))
                waste_var = node_vars['waste_var']
                self.model.Add(waste_var == total_prod - total_used)
                all_waste_vars.append(waste_var)
                
                # Z3互換性
                if 'waste_var' not in z3_node:
                     z3_dummy_waste_var = z3.Int(f"waste_m{m_src}_l{l_src}_k{k_src}")
                     z3_node['waste_var'] = z3_dummy_waste_var
            
            # 操作回数
            all_activity_vars.append(node_vars['is_active_var'])
            # 試薬
            all_reagent_vars.extend(node_vars.get('reagent_vars', []))

        # 2. ピアRノードの集計
        for i, or_peer_node in enumerate(self.peer_vars):
            z3_peer_node = self.problem.peer_nodes[i]

            # 廃棄物
            total_prod = or_peer_node['total_input_var'] # 0 or 2
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            waste_var = or_peer_node['waste_var']
            self.model.Add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            
            # Z3互換性
            if 'waste_var' not in z3_peer_node:
                 z3_dummy_waste_var = z3.Int(f"waste_peer_{i}")
                 z3_peer_node['waste_var'] = z3_dummy_waste_var

            # 操作回数
            all_activity_vars.append(or_peer_node['is_active_var'])

        # --- 目的変数の設定 ---
        total_waste = sum(all_waste_vars)
        total_operations = sum(all_activity_vars)
        total_reagents = sum(all_reagent_vars)

        if self.objective_mode == 'waste':
            self.model.Minimize(total_waste)
            return total_waste
        elif self.objective_mode == 'operations':
            self.model.Minimize(total_operations)
            return total_operations
        elif self.objective_mode == 'reagents':
            self.model.Minimize(total_reagents)
            return total_reagents
        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'. Must be 'waste', 'operations', or 'reagents'.")