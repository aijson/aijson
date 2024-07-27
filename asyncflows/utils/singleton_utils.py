import os


class SingletonContext:
    def __init__(self):
        self.entry_count = 0

    def enter(self):
        raise NotImplementedError

    def exit(self):
        raise NotImplementedError

    def __enter__(self):
        self.entry_count += 1
        if self.entry_count > 1:
            return
        self.enter()

    def __exit__(self, *args):
        self.entry_count -= 1
        if self.entry_count > 0:
            return
        self.exit()


class TempEnvContext(SingletonContext):
    def __init__(self, env_vars: dict[str, str | None]):
        super().__init__()
        self.env_vars = env_vars
        self.env_var_baks: None | dict[str, None | str] = None

    def enter(self):
        env_var_baks = {}
        for key, value in self.env_vars.items():
            if value is None:
                if key in os.environ:
                    env_var_baks[key] = os.environ.get(key)
                    del os.environ[key]
            else:
                env_var_baks[key] = os.environ.get(key)
                os.environ[key] = value
        self.env_var_baks = env_var_baks

    def exit(self):
        if self.env_var_baks is None:
            raise RuntimeError("Exit called before enter")
        for key, value in self.env_var_baks.items():
            if value is None:
                del os.environ[key]
            else:
                os.environ[key] = value
        self.env_var_baks = None
