#!/usr/bin/env python
import json
import sys
import yaml

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    log,
    relation_get,
    relation_ids,
    related_units,
    status_set,
    relation_set,
    is_leader,
    leader_get,
)
from charmhelpers.contrib.charmsupport import nrpe

import contrail_kubernetes_master_utils as utils
import common_utils
import docker_utils


hooks = Hooks()
config = config()


@hooks.hook("install.real")
def install():
    status_set('maintenance', 'Installing...')

    # TODO: try to remove this call
    common_utils.fix_hostname()

    docker_utils.install()
    status_set("blocked", "Missing relation to contrail-controller")


@hooks.hook("config-changed")
def config_changed():
    update_nrpe_config()
    _notify_contrail_kubernetes_node()

    # TODO: analyze changed params and raise exception if readonly params were changed

    docker_utils.config_changed()
    utils.update_charm_status()


@hooks.hook("contrail-controller-relation-joined")
def contrail_controller_joined(rel_id=None):
    settings = {'unit-type': 'kubernetes'}
    relation_set(relation_id=rel_id, relation_settings=settings)
    if is_leader():
        data = _get_orchestrator_info()
        relation_set(relation_id=rel_id, **data)


@hooks.hook("contrail-controller-relation-changed")
def contrail_controller_changed():
    data = relation_get()
    log("RelData: " + str(data))

    _update_config(data, "analytics_servers", "analytics-server")
    config.save()

    utils.update_charm_status()


@hooks.hook("contrail-controller-relation-departed")
def contrail_cotroller_departed():
    units = [unit for rid in relation_ids("contrail-controller")
                      for unit in related_units(rid)]
    if units:
        return

    utils.update_charm_status()
    status_set("blocked", "Missing relation to contrail-controller")


@hooks.hook("kube-api-endpoint-relation-changed")
def kube_api_endpoint_changed():
    data = relation_get()
    log("RelData: " + str(data))

    changed = _update_config(data, "kubernetes_api_server", "hostname")
    changed |= _update_config(data, "kubernetes_api_secure_port", "port")
    config.save()

    if is_leader():
        changed |= utils.update_kubernetes_token()
    if not changed:
        return
    # notify clients
    _notify_controller()
    # and update self
    utils.update_charm_status()


@hooks.hook("contrail-kubernetes-config-relation-joined")
def contrail_kubernetes_config_joined(rel_id=None):
    data = {"pod_subnets": config.get("pod_subnets")}
    relation_set(relation_id=rel_id, relation_settings=data)


@hooks.hook("update-status")
def update_status():
    # try to obtain token again if it's not set yet
    if not is_leader():
        return

    changed = utils.update_kubernetes_token()
    if not changed:
        return
    # notify clients
    _notify_controller()
    # and update self
    utils.update_charm_status()


def _update_config(data, key, data_key):
    if data_key in data:
        changed = config.get(key) != data[data_key]
        config[key] = data[data_key]
        return changed
    # absence of key in relation means that this key was not set in the relation
    # non-leader may send not all data
    # and it doesn't mean that key was unset
    return False


def _notify_contrail_kubernetes_node():
    for rid in relation_ids("contrail-kubernetes-config"):
        if related_units(rid):
            contrail_kubernetes_config_joined(rel_id=rid)


def _notify_controller():
    for rid in relation_ids("contrail-controller"):
        if related_units(rid):
            contrail_controller_joined(rel_id=rid)


def _get_orchestrator_info():
    info = {"cloud_orchestrator": "kubernetes"}

    def _add_to_info(key, func):
        value = func(key)
        if value:
            info[key] = value

    _add_to_info("kube_manager_token", leader_get)
    _add_to_info("kubernetes_api_server", config.get)
    _add_to_info("kubernetes_api_secure_port", config.get)
    return {"orchestrator-info": json.dumps(info)}


@hooks.hook("upgrade-charm")
def upgrade_charm():
    utils.update_charm_status()


@hooks.hook('nrpe-external-master-relation-changed')
def nrpe_external_master_relation_changed():
    update_nrpe_config()


def update_nrpe_config():
    plugins_dir = '/usr/local/lib/nagios/plugins'
    nrpe_compat = nrpe.NRPE()
    common_utils.rsync_nrpe_checks(plugins_dir)
    common_utils.add_nagios_to_sudoers()

    ctl_status_shortname = 'check_contrail_status_' + utils.MODULE
    nrpe_compat.add_check(
        shortname=ctl_status_shortname,
        description='Check contrail-status',
        check_cmd=common_utils.contrail_status_cmd(utils.MODULE, plugins_dir)
    )

    nrpe_compat.write()


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log("Unknown hook {} - skipping.".format(e))


if __name__ == "__main__":
    main()
