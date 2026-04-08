from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import oasis
from camel.models import ModelFactory
from camel.types import ModelPlatformType


def _load_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--database", required=True)
    return parser.parse_args()


def _build_model():
    llm_base_url = _get_env("OASIS_LLM_BASE_URL")
    llm_api_key = _get_env("OASIS_LLM_API_KEY")
    llm_model = _get_env("OASIS_LLM_MODEL")
    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=llm_model,
        url=llm_base_url,
        api_key=llm_api_key,
        model_config_dict={"temperature": 0.2},
    )


def _get_env(name: str) -> str:
    import os

    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable {name}.")
    return value


async def _run(config_path: Path, report_path: Path, database_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    model = _build_model()
    available_actions = [
        getattr(oasis.ActionType, action)
        for action in config.get("available_actions", [])
        if hasattr(oasis.ActionType, action)
    ]
    if not available_actions:
        available_actions = [oasis.ActionType.DO_NOTHING]

    agent_graph = oasis.AgentGraph()
    agent_profiles = list(config.get("agent_profiles", []) or [])
    agent_count = int(config.get("agent_count", 0) or 0)
    platform = str(config.get("platform", "reddit")).strip().lower()
    for index, profile in enumerate(agent_profiles[: min(agent_count or len(agent_profiles), 12)]):
        agent = _build_social_agent(
            agent_id=index,
            profile=profile,
            agent_graph=agent_graph,
            model=model,
            available_actions=available_actions,
            platform=platform,
        )
        agent_graph.add_agent(agent)

    env = oasis.make(
        agent_graph=agent_graph,
        platform=getattr(oasis.DefaultPlatformType, platform.upper(), oasis.DefaultPlatformType.REDDIT),
        database_path=str(database_path),
    )

    await env.reset()
    try:
        for _ in range(2):
            actions = {agent: oasis.LLMAction() for _, agent in env.agent_graph.get_agents()}
            if actions:
                await env.step(actions)
    finally:
        await env.close()

    report_path.write_text(
        json.dumps(
            {
                "platform": platform,
                "agent_count": agent_count,
                "time_horizon": config.get("time_horizon"),
                "topic": config.get("topic"),
                "objective": config.get("objective"),
                "execution_mode": "docker",
                "model_source": _get_env("OASIS_LLM_SOURCE"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = _load_args()
    asyncio.run(
        _run(
            config_path=Path(args.config),
            report_path=Path(args.report),
            database_path=Path(args.database),
        )
    )


def _build_social_agent(*, agent_id: int, profile: dict, agent_graph, model, available_actions: list, platform: str):
    oasis_user_info = _build_oasis_user_info(profile.get("user_info", {}), platform=platform)
    kwargs = {
        "agent_id": agent_id,
        "user_info": oasis_user_info,
        "agent_graph": agent_graph,
        "model": model,
        "available_actions": available_actions,
    }
    try:
        return oasis.SocialAgent(single_iteration=False, **kwargs)
    except TypeError:
        return oasis.SocialAgent(**kwargs)


def _build_oasis_user_info(user_info: dict, *, platform: str):
    handle = str(user_info.get("handle") or user_info.get("name") or "synthetic_agent").strip()
    bio = str(user_info.get("bio") or user_info.get("description") or "Synthetic agent profile.").strip()
    recsys_type = "twitter" if str(platform).lower() == "twitter" else "reddit"
    return oasis.UserInfo(
        user_name=handle,
        name=handle,
        description=bio,
        recsys_type=recsys_type,
        profile={
            "other_info": {
                "user_profile": bio,
                "gender": str(user_info.get("gender") or "unknown"),
                "age": int(user_info.get("age") or 30),
                "mbti": str(user_info.get("mbti") or "INTJ"),
                "country": str(user_info.get("country") or "unknown"),
            }
        },
    )


if __name__ == "__main__":
    main()
