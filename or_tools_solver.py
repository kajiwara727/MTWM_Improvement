import time
import sys
from ortools.sat.python import cp_model
from reporting.reporter import SolutionReporter
from config import MAX_SHARING_VOLUME, MAX_MIXER_SIZE
from utils.helpers import (
    create_dfmm_node_name,
    create_intra_key,
    create_inter_key,
    create_peer_key,
    parse_sharing_key,
)

sys.setrecursionlimit(2000)
MAX_PRODUCT_BOUND = 50000

class OrToolsSolutionModel:
    """
    Or-Toolsソルバーの解を保持し、SolutionReporterが要求する形式で
    データを抽出・提供する責務を持つクラス。
    """

    def __init__(self, problem, solver, forest_vars, peer_vars):
        self.problem = problem
        self.solver = solver
        self.forest_vars = forest_vars
        self.peer_vars = peer_vars
        self.num_reagents = problem.num_reagents

    def _v(self, or_tools_var):
        """ヘルパー: Or-Toolsの変数値を取得する (Noneの場合は0)"""
        val = self.solver.Value(or_tools_var)
        return int(val) if val is not None else 0

    def analyze(self):
        """
        SolutionReporter.analyze_solution() のロジックを
        Or-Toolsの解から直接実行する。
        """
        results = {
            "total_operations": 0,
            "total_reagent_units": 0,
            "total_waste": 0,
            "reagent_usage": {},
            "nodes_details": [],
        }

        # 1. DFMMノード
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node_vars in enumerate(nodes):
                    total_input = self._v(node_vars["total_input_var"])
                    if total_input == 0:
                        continue
                    results["total_operations"] += 1
                    reagent_vals = [self._v(r) for r in node_vars["reagent_vars"]]
                    for r_idx, val in enumerate(reagent_vals):
                        if val > 0:
                            results["total_reagent_units"] += val
                            results["reagent_usage"][r_idx] = (
                                results["reagent_usage"].get(r_idx, 0) + val
                            )
                    if level != 0:
                        results["total_waste"] += self._v(node_vars["waste_var"])
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    results["nodes_details"].append(
                        {
                            "target_id": target_idx,
                            "level": level,
                            "name": node_name,
                            "total_input": total_input,
                            "ratio_composition": [
                                self._v(r) for r in node_vars["ratio_vars"]
                            ],
                            "mixing_str": self._generate_mixing_description(
                                node_vars, target_idx
                            ),
                        }
                    )

        # 2. ピアRノード
        for i, peer_node_vars in enumerate(self.peer_vars):
            total_input = self._v(peer_node_vars["total_input_var"])
            if total_input == 0:
                continue

            results["total_operations"] += 1
            results["total_waste"] += self._v(peer_node_vars["waste_var"])

            z3_peer_node = self.problem.peer_nodes[i]
            m_a, l_a, k_a = z3_peer_node["source_a_id"]
            name_a = create_dfmm_node_name(m_a, l_a, k_a)
            m_b, l_b, k_b = z3_peer_node["source_b_id"]
            name_b = create_dfmm_node_name(m_b, l_b, k_b)
            mixing_str = f"1 x {name_a} + 1 x {name_b}"
            level_eff = (l_a + l_b) / 2.0 - 0.5

            results["nodes_details"].append(
                {
                    "target_id": -1,
                    "level": level_eff,
                    "name": peer_node_vars["name"],
                    "total_input": total_input,
                    "ratio_composition": [
                        self._v(r) for r in peer_node_vars["ratio_vars"]
                    ],
                    "mixing_str": mixing_str,
                }
            )

        results["nodes_details"].sort(key=lambda x: (x["target_id"], x["level"]))
        return results

    def _generate_mixing_description(self, node_vars, target_idx):
        """Or-Toolsの変数から直接、混合文字列を生成する。"""
        desc = []
        for r_idx, r_var in enumerate(node_vars.get("reagent_vars", [])):
            if (val := self._v(r_var)) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
        for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
            if (val := self._v(w_var)) > 0:
                key_no_prefix = key.replace("from_", "")
                parsed = parse_sharing_key(key_no_prefix)
                node_name = create_dfmm_node_name(
                    target_idx, parsed["level"], parsed["node_idx"]
                )
                desc.append(f"{val} x {node_name}")
        for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
            if (val := self._v(w_var)) > 0:
                key_no_prefix = key.replace("from_", "")
                parsed = parse_sharing_key(key_no_prefix)
                if parsed["type"] == "PEER":
                    peer_node_name = self.problem.peer_nodes[parsed["idx"]]["name"]
                    desc.append(f"{val} x {peer_node_name}")
                elif parsed["type"] == "DFMM":
                    node_name = create_dfmm_node_name(
                        parsed["target_idx"], parsed["level"], parsed["node_idx"]
                    )
                    desc.append(f"{val} x {node_name}")
        return " + ".join(desc)


class OrToolsSolver:

    def __init__(self, problem, objective_mode="waste"):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.forest_vars = []
        self.peer_vars = []
        self._set_variables_and_constraints()

    def solve(self):
        start_time = time.time()
        print(
            f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---"
        )
        status = self.solver.Solve(self.model)
        elapsed_time = time.time() - start_time
        best_model = None
        best_value = None
        best_analysis = None
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            print(
                f"Or-Tools found an optimal solution with {self.objective_mode}: {int(best_value)}"
            )
            best_model = OrToolsSolutionModel(
                self.problem, self.solver, self.forest_vars, self.peer_vars
            )
            best_analysis = best_model.analyze()
        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
            if status == cp_model.INFEASIBLE:
                print("No feasible solution found.")
        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time

    def _set_variables_and_constraints(self):
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_range_constraints()
        self._set_activity_constraints()
        self._set_peer_mixing_constraints()
        self.objective_variable = self._set_objective_function()

    def _define_or_tools_variables(self):
        max_ratio_sum = (
            max(sum(t["ratios"]) for t in self.problem.targets_config)
            if self.problem.targets_config
            else 1
        )
        MAX_BOUND = max_ratio_sum * (MAX_MIXER_SIZE or 1) * 10
        if MAX_BOUND < 900:
            MAX_BOUND = 900
        for target_idx, z3_tree in enumerate(self.problem.forest):
            tree_data = {}
            for level, z3_nodes in z3_tree.items():
                level_nodes = []
                for node_idx, z3_node in enumerate(z3_nodes):
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    node_vars = {
                        "ratio_vars": [
                            self.model.NewIntVar(
                                0, MAX_BOUND, f"ratio_{node_name}_r{t}"
                            )
                            for t in range(self.problem.num_reagents)
                        ],
                        "reagent_vars": [
                            self.model.NewIntVar(
                                0, MAX_BOUND, f"reagent_vol_{node_name}_r{t}"
                            )
                            for t in range(self.problem.num_reagents)
                        ],
                        "intra_sharing_vars": {},
                        "inter_sharing_vars": {},
                        "total_input_var": self.model.NewIntVar(
                            0, MAX_BOUND, f"TotalInput_{node_name}"
                        ),
                        "is_active_var": self.model.NewBoolVar(f"IsActive_{node_name}"),
                        "waste_var": self.model.NewIntVar(
                            0, MAX_BOUND, f"waste_{node_name}"
                        ),
                    }
                    max_sharing_vol = min(MAX_BOUND, MAX_SHARING_VOLUME or MAX_BOUND)
                    for key in z3_node.get("intra_sharing_vars", {}).keys():
                        share_name = (
                            f"share_intra_t{target_idx}_l{level}_k{node_idx}_{key}"
                        )
                        node_vars["intra_sharing_vars"][key] = self.model.NewIntVar(
                            0, max_sharing_vol, share_name
                        )
                    for key in z3_node.get("inter_sharing_vars", {}).keys():
                        share_name = (
                            f"share_inter_t{target_idx}_l{level}_k{node_idx}_{key}"
                        )
                        node_vars["inter_sharing_vars"][key] = self.model.NewIntVar(
                            0, max_sharing_vol, share_name
                        )
                    level_nodes.append(node_vars)
                tree_data[level] = level_nodes
            self.forest_vars.append(tree_data)
        for i, z3_peer_node in enumerate(self.problem.peer_nodes):
            name = z3_peer_node["name"]
            p_val = z3_peer_node["p_value"]
            node_vars = {
                "name": name,
                "p_value": p_val,
                "source_a_id": z3_peer_node["source_a_id"],
                "source_b_id": z3_peer_node["source_b_id"],
                "ratio_vars": [
                    self.model.NewIntVar(0, p_val, f"ratio_{name}_r{t}")
                    for t in range(self.problem.num_reagents)
                ],
                "input_vars": {
                    "from_a": self.model.NewIntVar(0, 1, f"share_peer_a_to_{name}"),
                    "from_b": self.model.NewIntVar(0, 1, f"share_peer_b_to_{name}"),
                },
                "total_input_var": self.model.NewIntVar(0, 2, f"TotalInput_{name}"),
                "is_active_var": self.model.NewBoolVar(f"IsActive_{name}"),
                "waste_var": self.model.NewIntVar(0, 2, f"waste_{name}"),
            }
            self.peer_vars.append(node_vars)

    def _get_input_vars(self, node_vars):
        return (
            node_vars.get("reagent_vars", [])
            + list(node_vars.get("intra_sharing_vars", {}).values())
            + list(node_vars.get("inter_sharing_vars", {}).values())
        )

    def _get_outgoing_vars(self, src_target_idx, src_level, src_node_idx):
        outgoing = []
        key_intra = f"from_{create_intra_key(src_level, src_node_idx)}"
        key_inter = f"from_{create_inter_key(src_target_idx, src_level, src_node_idx)}"
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if src_target_idx == dst_target_idx and key_intra in node_dst.get(
                        "intra_sharing_vars", {}
                    ):
                        outgoing.append(node_dst["intra_sharing_vars"][key_intra])
                    elif src_target_idx != dst_target_idx and key_inter in node_dst.get(
                        "inter_sharing_vars", {}
                    ):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        for or_peer_node in self.peer_vars:
            if (
                src_target_idx,
                src_level,
                src_node_idx,
            ) == or_peer_node["source_a_id"]:
                outgoing.append(or_peer_node["input_vars"]["from_a"])
            if (
                src_target_idx,
                src_level,
                src_node_idx,
            ) == or_peer_node["source_b_id"]:
                outgoing.append(or_peer_node["input_vars"]["from_b"])
        return outgoing

    def _get_outgoing_vars_from_peer(self, peer_node_index):
        outgoing = []
        key_inter = f"from_{create_peer_key(peer_node_index)}"
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        return outgoing

    def _iterate_all_nodes(self):
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    yield target_idx, level, node_idx, node

    def _set_initial_constraints(self):
        for target_idx, target in enumerate(self.problem.targets_config):
            root_vars = self.forest_vars[target_idx][0][0]
            for reagent_idx in range(self.problem.num_reagents):
                self.model.Add(
                    root_vars["ratio_vars"][reagent_idx]
                    == target["ratios"][reagent_idx]
                )

    def _set_conservation_constraints(self):
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            total_produced = node_vars["total_input_var"]
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))

    def _set_concentration_constraints(self):
        for (
            dst_target_idx,
            dst_level,
            dst_node_idx,
            node_vars,
        ) in self._iterate_all_nodes():
            p_dst = self.problem.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.problem.targets_config[dst_target_idx]["factors"][dst_level]
            for reagent_idx in range(self.problem.num_reagents):
                lhs = f_dst * node_vars["ratio_vars"][reagent_idx]
                rhs_terms = [p_dst * node_vars["reagent_vars"][reagent_idx]]
                for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed_key = parse_sharing_key(key_no_prefix)
                    l_src = parsed_key["level"]
                    k_src = parsed_key["node_idx"]
                    r_src = self.forest_vars[dst_target_idx][l_src][k_src][
                        "ratio_vars"
                    ][reagent_idx]
                    p_src = self.problem.p_value_maps[dst_target_idx][(l_src, k_src)]
                    prod_name = f"Prod_intra_t{dst_target_idx}l{dst_level}k{dst_node_idx}_r{reagent_idx}_from_{key}"
                    product_var = self.model.NewIntVar(0, MAX_PRODUCT_BOUND, prod_name)
                    self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
                    scale_factor = p_dst // p_src
                    rhs_terms.append(product_var * scale_factor)
                for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed_key = parse_sharing_key(key_no_prefix)
                    if parsed_key["type"] == "PEER":
                        r_node_idx = parsed_key["idx"]
                        or_peer_node = self.peer_vars[r_node_idx]
                        r_src = or_peer_node["ratio_vars"][reagent_idx]
                        p_src = or_peer_node["p_value"]
                    else:
                        m_src = parsed_key["target_idx"]
                        l_src = parsed_key["level"]
                        k_src = parsed_key["node_idx"]
                        r_src = self.forest_vars[m_src][l_src][k_src]["ratio_vars"][
                            reagent_idx
                        ]
                        p_src = self.problem.p_value_maps[m_src][(l_src, k_src)]
                    prod_name = f"Prod_inter_t{dst_target_idx}l{dst_level}k{dst_node_idx}_r{reagent_idx}_from_{key}"
                    product_var = self.model.NewIntVar(0, MAX_PRODUCT_BOUND, prod_name)
                    self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
                    scale_factor = p_dst // p_src
                    rhs_terms.append(product_var * scale_factor)
                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            self.model.Add(sum(node_vars["ratio_vars"]) == p_node)

    def _set_leaf_node_constraints(self):
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            f_node = self.problem.targets_config[target_idx]["factors"][level]
            if p_node == f_node:
                for reagent_idx in range(self.problem.num_reagents):
                    self.model.Add(
                        node_vars["ratio_vars"][reagent_idx]
                        == node_vars["reagent_vars"][reagent_idx]
                    )

    def _set_mixer_capacity_constraints(self):
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[target_idx]["factors"][level]
            total_sum = node_vars["total_input_var"]
            is_active = node_vars["is_active_var"]
            if level == 0:
                self.model.Add(total_sum == f_value)
            else:
                self.model.Add(total_sum == f_value).OnlyEnforceIf(is_active)
                self.model.Add(total_sum == 0).OnlyEnforceIf(is_active.Not())

    def _set_range_constraints(self):
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            upper_bound = self.problem.targets_config[target_idx]["factors"][level] - 1
            for var in node_vars.get("reagent_vars", []):
                self.model.Add(var <= upper_bound)

    def _set_activity_constraints(self):
        for (
            src_target_idx,
            src_level,
            src_node_idx,
            node_vars,
        ) in self._iterate_all_nodes():
            if src_level == 0:
                continue
            total_prod = node_vars["total_input_var"]
            total_used = sum(
                self._get_outgoing_vars(src_target_idx, src_level, src_node_idx)
            )
            is_active = node_vars["is_active_var"]
            is_used_name = f"IsUsed_t{src_target_idx}_l{src_level}_k{src_node_idx}"
            is_used = self.model.NewBoolVar(is_used_name)
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_used)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_used.Not())
            self.model.AddImplication(is_active, is_used)
        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node["total_input_var"]
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            is_active = or_peer_node["is_active_var"]
            is_used = self.model.NewBoolVar(f"IsUsed_Peer_{i}")
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_used)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_used.Not())
            self.model.AddImplication(is_active, is_used)

    def _set_peer_mixing_constraints(self):
        for i, or_peer_node in enumerate(self.peer_vars):
            total_input = or_peer_node["total_input_var"]
            is_active = or_peer_node["is_active_var"]
            w_a = or_peer_node["input_vars"]["from_a"]
            w_b = or_peer_node["input_vars"]["from_b"]
            self.model.Add(total_input == w_a + w_b)
            self.model.Add(total_input == 2).OnlyEnforceIf(is_active)
            self.model.Add(w_a == 1).OnlyEnforceIf(is_active)
            self.model.Add(w_b == 1).OnlyEnforceIf(is_active)
            self.model.Add(total_input == 0).OnlyEnforceIf(is_active.Not())
            self.model.Add(w_a == 0).OnlyEnforceIf(is_active.Not())
            self.model.Add(w_b == 0).OnlyEnforceIf(is_active.Not())
            p_val = or_peer_node["p_value"]
            r_new_vars = or_peer_node["ratio_vars"]
            self.model.Add(sum(r_new_vars) == p_val).OnlyEnforceIf(is_active)
            self.model.Add(sum(r_new_vars) == 0).OnlyEnforceIf(is_active.Not())
            m_a, l_a, k_a = or_peer_node["source_a_id"]
            r_a_vars = self.forest_vars[m_a][l_a][k_a]["ratio_vars"]
            m_b, l_b, k_b = or_peer_node["source_b_id"]
            r_b_vars = self.forest_vars[m_b][l_b][k_b]["ratio_vars"]
            for reagent_idx in range(self.problem.num_reagents):
                lhs = 2 * r_new_vars[reagent_idx]
                rhs = r_a_vars[reagent_idx] + r_b_vars[reagent_idx]
                self.model.Add(lhs == rhs).OnlyEnforceIf(is_active)

    def _set_objective_function(self):
        """目的変数を定義する。"""

        all_waste_vars = []
        all_activity_vars = []
        all_reagent_vars = []

        # 1. DFMMノードの集計
        for (
            src_target_idx,
            src_level,
            src_node_idx,
            node_vars,
        ) in self._iterate_all_nodes():
            if src_level != 0:
                total_prod = node_vars["total_input_var"]
                total_used = sum(
                    self._get_outgoing_vars(src_target_idx, src_level, src_node_idx)
                )
                waste_var = node_vars["waste_var"]
                self.model.Add(waste_var == total_prod - total_used)
                all_waste_vars.append(waste_var)

            all_activity_vars.append(node_vars["is_active_var"])
            all_reagent_vars.extend(node_vars.get("reagent_vars", []))

        # 2. ピアRノードの集計
        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node["total_input_var"]
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            waste_var = or_peer_node["waste_var"]
            self.model.Add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            all_activity_vars.append(or_peer_node["is_active_var"])

        # 3. 目的変数の設定 
        total_waste = sum(all_waste_vars)
        total_operations = sum(all_activity_vars)
        total_reagents = sum(all_reagent_vars)

        if self.objective_mode == "waste":
            self.model.Minimize(total_waste)
            return total_waste
        elif self.objective_mode == "operations":
            self.model.Minimize(total_operations)
            return total_operations
        elif self.objective_mode == "reagents":
            self.model.Minimize(total_reagents)
            return total_reagents
        else:
            raise ValueError(
                f"Unknown optimization mode: '{self.objective_mode}'. Must be 'waste', 'operations', or 'reagents'."
            )
