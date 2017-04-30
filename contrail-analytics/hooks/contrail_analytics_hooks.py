#!/usr/bin/env python
import sys

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
)

from charmhelpers.fetch import (
    apt_install,
    apt_upgrade,
    apt_update
)

from contrail_analytics_utils import (
    update_charm_status,
    CONTAINER_NAME,
    fix_hostname,
    get_ip
)

from docker_utils import (
    add_docker_repo,
    DOCKER_PACKAGES,
    is_container_launched,
    load_docker_image,
)


PACKAGES = ["python", "python-yaml", "python-apt", "python-netifaces"]

hooks = Hooks()
config = config()


@hooks.hook()
def install():
    apt_upgrade(fatal=True, dist=True)
    add_docker_repo()
    apt_update(fatal=False)
    apt_install(PACKAGES + DOCKER_PACKAGES, fatal=True)

    # TODO: try to remove this call
    fix_hostname()

    load_docker_image(CONTAINER_NAME)
    update_charm_status()


@hooks.hook("config-changed")
def config_changed():
    update_charm_status()


def _value_changed(rel_key, cfg_key):
    value = relation_get(rel_key)
    if value is not None:
        config[cfg_key] = value
    else:
        config.pop(cfg_key, None)


@hooks.hook("contrail-analytics-relation-joined")
def contrail_analytics_joined():
    settings = {'private-address': get_ip()}
    relation_set(relation_settings=settings)


@hooks.hook("contrail-analytics-relation-changed")
def contrail_analytics_changed():
    _value_changed("multi-tenancy", "multi_tenancy")
    _value_changed("auth-info", "auth_info")
    _value_changed("cloud-orchestrator", "cloud_orchestrator")
    # TODO: handle changing of all values
    # TODO: set error if orchestrator is changing and container was started
    update_charm_status()


@hooks.hook("contrail-analytics-relation-departed")
def contrail_analytics_departed():
    units = [unit for rid in relation_ids("contrail-controller")
                  for unit in related_units(rid)]
    if not units:
        config.pop("auth_info", None)
        config.pop("multi_tenancy", None)
        config.pop("cloud_orchestrator", None)
        if is_container_launched(CONTAINER_NAME):
            status_set(
                "error",
                "Container is present but cloud orchestrator was disappeared."
                " Please kill container by yourself or restore it.")
    update_charm_status()


@hooks.hook("contrail-analyticsdb-relation-joined")
@hooks.hook("contrail-analyticsdb-relation-departed")
def contrail_analyticsdb_relation():
    update_charm_status()


@hooks.hook("analytics-cluster-relation-joined")
def analytics_cluster_joined():
    settings = {'private-address': get_ip()}
    relation_set(relation_settings=settings)

    update_charm_status()


@hooks.hook("update-status")
def update_status():
    update_charm_status(update_config=False)


@hooks.hook("upgrade-charm")
def upgrade_charm():
    if not is_container_launched(CONTAINER_NAME):
        load_docker_image(CONTAINER_NAME)
        # NOTE: image can not be deleted if container is running.
        # TODO: think about killing the container

    # TODO: this hook can be fired when either resource changed or charm code
    # changed. so if code was changed then we may need to update config
    update_charm_status()


@hooks.hook("start")
@hooks.hook("stop")
def todo():
    # TODO: think about it
    pass


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log("Unknown hook {} - skipping.".format(e))


if __name__ == "__main__":
    main()
