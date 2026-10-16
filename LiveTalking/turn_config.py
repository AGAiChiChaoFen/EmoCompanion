###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：turn_config.py
#  说明：TURN/ICE 配置解析与 /rtc_config 路由。
#  许可证：Apache License 2.0
###############################################################################

from __future__ import annotations

import re
from typing import Any

from aiohttp import web
from aiortc import RTCIceServer

from logger import logger

opt: Any = None


def configure_turn_runtime(options: Any) -> None:
    """注入 app.py 启动阶段解析出的 TURN/ICE 配置。"""
    global opt
    opt = options


def parse_turn_urls(turn_url: str):
    return [u.strip() for u in re.split(r'[\s,]+', turn_url.strip()) if u.strip()]


def build_turn_urls_from_host():
    if not opt.turn_host:
        return []

    turn_urls = []
    if opt.turn_enable_udp:
        turn_urls.append(f'turn:{opt.turn_host}:{opt.turn_port}?transport=udp')
    if opt.turn_enable_tcp:
        turn_urls.append(f'turn:{opt.turn_host}:{opt.turn_port}?transport=tcp')
    if opt.turn_enable_tls:
        turn_urls.append(f'turns:{opt.turn_host}:{opt.turn_tls_port}?transport=tcp')

    return turn_urls


def resolve_turn_urls():
    if opt.turn_url:
        return parse_turn_urls(opt.turn_url)
    return build_turn_urls_from_host()


def build_frontend_ice_servers(turn_urls):
    ice_servers = []

    # 保留 STUN 入口：当前端策略为 all 时，允许直连候选优先尝试。
    if opt.turn_host:
        ice_servers.append({"urls": [f"stun:{opt.turn_host}:{opt.turn_port}"]})

    if not (turn_urls and opt.turn_username and opt.turn_password):
        return ice_servers

    # 按传输协议拆分 TURN 地址，提升不同浏览器下的候选协商兼容性。
    udp_urls = [u for u in turn_urls if u.startswith('turn:') and 'transport=udp' in u]
    tcp_urls = [u for u in turn_urls if (u.startswith('turn:') and 'transport=tcp' in u) or u.startswith('turns:')]
    rest_urls = [u for u in turn_urls if u not in udp_urls and u not in tcp_urls]

    def _append_server(url_group):
        if not url_group:
            return
        ice_servers.append(
            {
                "urls": url_group if len(url_group) > 1 else url_group[0],
                "username": opt.turn_username,
                "credential": opt.turn_password,
            }
        )

    _append_server(udp_urls)
    _append_server(tcp_urls)
    _append_server(rest_urls)

    return ice_servers


def build_ice_servers():
    ice_servers = []
    turn_urls = resolve_turn_urls()

    if turn_urls:
        if not opt.turn_username or not opt.turn_password:
            logger.warning('TURN urls are set but turn_username/turn_password is empty, ignore TURN config')
        else:
            ice_servers.append(
                RTCIceServer(
                    urls=turn_urls if len(turn_urls) > 1 else turn_urls[0],
                    username=opt.turn_username,
                    credential=opt.turn_password,
                )
            )

    if not ice_servers:
        raise ValueError('TURN is required in this deployment, please configure --turn_url (or --turn_host) --turn_username --turn_password')

    logger.info('ICE servers: %s', [s.urls for s in ice_servers])
    return ice_servers


async def rtc_config(request):
    turn_urls = resolve_turn_urls()
    ice_servers = build_frontend_ice_servers(turn_urls)

    return web.json_response(
        {
            "iceServers": ice_servers,
            "iceTransportPolicy": opt.ice_transport_policy,
        }
    )
