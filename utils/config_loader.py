# utils/config_loader.py
import config


class Config:
    """
    設定ファイル (config.py) から値を読み込み、アプリケーション全体で
    一元的に管理するためのクラス。
    これにより、設定へのアクセスが容易になり、コードの他の部分から
    設定ファイルの詳細を隠蔽します。
    """

    # config.py から主要な設定値をクラス属性として読み込む
    RUN_NAME = config.RUN_NAME
    MODE = config.FACTOR_EXECUTION_MODE
    OPTIMIZATION_MODE = config.OPTIMIZATION_MODE
    CONFIG_LOAD_FILE = config.CONFIG_LOAD_FILE
    ENABLE_VISUALIZATION = config.ENABLE_VISUALIZATION
    MAX_SHARING_VOLUME = config.MAX_SHARING_VOLUME
    MAX_LEVEL_DIFF = config.MAX_LEVEL_DIFF
    MAX_MIXER_SIZE = config.MAX_MIXER_SIZE
    # RANDOM_SETTINGS = config.RANDOM_SETTINGS (削除)

    # 'random' モード用の設定を個別に読み込む
    RANDOM_T_REAGENTS = config.RANDOM_T_REAGENTS
    RANDOM_N_TARGETS = config.RANDOM_N_TARGETS
    RANDOM_K_RUNS = config.RANDOM_K_RUNS
    RANDOM_S_RATIO_SUM_SEQUENCE = config.RANDOM_S_RATIO_SUM_SEQUENCE
    RANDOM_S_RATIO_SUM_CANDIDATES = config.RANDOM_S_RATIO_SUM_CANDIDATES
    RANDOM_S_RATIO_SUM_DEFAULT = config.RANDOM_S_RATIO_SUM_DEFAULT

    @staticmethod
    def get_targets_config():
        """
        現在の実行モード (MODE) に応じて、config.py から適切な
        ターゲット設定リストを返します。
        静的メソッドなので、インスタンス化せずに呼び出せます (Config.get_targets_config())。

        Returns:
            list: ターゲット設定のリスト。

        Raises:
            ValueError: config.pyで未知のモードが指定されている場合に発生します。
        """
        if Config.MODE in ["auto", "auto_permutations"]:
            # 'auto'系モードの場合は、TARGETS_FOR_AUTO_MODE を使用
            return config.TARGETS_FOR_AUTO_MODE
        elif Config.MODE == "manual":
            # 'manual'モードの場合は、TARGETS_FOR_MANUAL_MODE を使用
            return config.TARGETS_FOR_MANUAL_MODE
        elif Config.MODE == "random":
            # 'random'モードではターゲット設定は動的に生成されるため、ここでは空リストを返す
            return []
        else:
            # いずれにも該当しない場合はエラー
            raise ValueError(
                f"Unknown FACTOR_EXECUTION_MODE in config.py: '{Config.MODE}'"
            )
