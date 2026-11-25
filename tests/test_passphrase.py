import pytest

from claude_cfg.errors import PassphraseUnavailableError
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR, PassphraseResolver

CFG_WITH_PASSPHRASE = {"encryption": {"enabled": True, "passphrase": "from-config"}}
CFG_WITHOUT_PASSPHRASE = {"encryption": {"enabled": True}}


def _resolver(cfg, environ=None, prompt_value="from-prompt", tty=True, prompts=None):
    def prompt():
        if prompts is not None:
            prompts.append(1)
        return prompt_value

    return PassphraseResolver(
        cfg, environ=environ or {}, prompt=prompt, stdin_is_tty=lambda: tty
    )


def test_env_var_wins_over_config_and_prompt():
    prompts = []
    resolver = _resolver(
        CFG_WITH_PASSPHRASE, environ={PASSPHRASE_ENV_VAR: "from-env"}, prompts=prompts
    )
    assert resolver.resolve() == "from-env"
    assert prompts == []


def test_config_wins_over_prompt():
    prompts = []
    assert _resolver(CFG_WITH_PASSPHRASE, prompts=prompts).resolve() == "from-config"
    assert prompts == []


def test_empty_env_var_is_ignored():
    resolver = _resolver(CFG_WITH_PASSPHRASE, environ={PASSPHRASE_ENV_VAR: ""})
    assert resolver.resolve() == "from-config"


def test_prompt_used_when_stdin_is_a_terminal():
    assert _resolver(CFG_WITHOUT_PASSPHRASE, tty=True).resolve() == "from-prompt"


def test_no_terminal_raises_error_naming_the_env_var():
    prompts = []
    resolver = _resolver(CFG_WITHOUT_PASSPHRASE, tty=False, prompts=prompts)
    with pytest.raises(PassphraseUnavailableError, match=PASSPHRASE_ENV_VAR):
        resolver.resolve()
    assert prompts == []


def test_empty_prompt_answer_raises():
    resolver = _resolver(CFG_WITHOUT_PASSPHRASE, prompt_value="", tty=True)
    with pytest.raises(PassphraseUnavailableError):
        resolver.resolve()


def test_config_without_encryption_section_still_resolves_from_env():
    resolver = _resolver({}, environ={PASSPHRASE_ENV_VAR: "from-env"}, tty=False)
    assert resolver.resolve() == "from-env"
