"""Use uvicorn server.app:create --factory. Real adapters are explicit."""
import importlib
import os

from server.gateway.service import create_app


def create():
    token = os.environ.get("SA_GATEWAY_TOKEN", "")
    demo = os.environ.get("SA_DEMO") == "1"
    if demo:
        from server.gateway.fixtures import demo_handlers
        return create_app(
            token=token, model_version="modelset-demo", config_version="rules-demo",
            dimension=2, handlers=demo_handlers(), demo=True,
        )
    factory_name = os.environ.get("SA_MODULE_FACTORY")
    model_version = os.environ.get("SA_MODEL_VERSION", "unconfigured")
    config_version = os.environ.get("SA_CONFIG_VERSION", "unconfigured")
    dimension = int(os.environ.get("SA_VECTOR_DIMENSION", "384"))
    handlers = {}
    module_errors = {}
    if factory_name == "server.modules.integration:create_handlers":
        from server.modules.integration import load_registry
        manifest, handlers, module_errors = load_registry()
        if manifest is not None:
            model_version, config_version = manifest["model_version"], manifest["config_version"]
            dimension = manifest["config"]["dimension"]
    elif factory_name:
        module, separator, name = factory_name.partition(":")
        if not separator:
            raise ValueError("SA_MODULE_FACTORY must be package.module:function")
        handlers = getattr(importlib.import_module(module), name)()
    app = create_app(
        token=token, model_version=model_version,
        config_version=config_version,
        dimension=dimension, handlers=handlers,
    )
    app.state.module_errors = module_errors
    return app
