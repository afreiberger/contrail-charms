#!/usr/bin/env python

from subprocess import (
    CalledProcessError,
    check_call,
    check_output
)
import sys

import yaml

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    resource_get,
    log,
    status_set
)

from charmhelpers.fetch import (
    apt_install,
    apt_upgrade
)

from contrail_analyticsdb_utils import (
    fix_hostname,
    write_analyticsdb_config
)

PACKAGES = [ "docker.io" ]


hooks = Hooks()
config = config()

@hooks.hook("config-changed")
def config_changed():
    set_status()
    return None

def config_get(key):
    try:
        return config[key]
    except KeyError:
        return None

def set_status():
  result = check_output(["/usr/bin/docker",
                         "inspect",
                         "-f",
                         "{{.State.Running}}",
                         "contrail-analyticsdb"
                         ])
  if result:
      status_set("active", "Unit ready")
  else:
      status_set("blocked", "Control container is not running")

def load_docker_image():
    img_path = resource_get("contrail-analyticsdb")
    check_call(["/usr/bin/docker",
                "load",
                "-i",
                img_path,
                ])

def launch_docker_image():
    image_id = None
    output =  check_output(["docker",
                            "images",
                            ])
    output = output.split('\n')[:-1]
    for line in output:
        if "contrail-analyticsdb" in line.split()[0]:
            image_id = line.split()[2].strip()
    if image_id:
        check_call(["/usr/bin/docker",
                    "run",
                    "--net=host",
                    "--cap-add=AUDIT_WRITE",
                    "--privileged",
                    "--env='CLOUD_ORCHESTRATOR=kubernetes'",
                    "--name=contrail-analyticsdb",
                    "-itd",
                    image_id
                   ])
    else:
        log("contrail-analyticsdb docker image is not available")

@hooks.hook()
def install():
    fix_hostname()
    apt_upgrade(fatal=True, dist=True)
    apt_install(PACKAGES, fatal=True)
    load_docker_image()
    launch_docker_image()
                
@hooks.hook("contrail-control-relation-joined")
def control_joined():
   config["control-ready"] = True
   write_analyticsdb_config()

@hooks.hook("contrail-lb-relation-joined")
def lb_joined():
   config["lb-ready"] = True
   write_analyticsdb_config()

@hooks.hook("contrail-control-relation-departed")
def control_departed():
   config["control-ready"] = False

@hooks.hook("contrail-lb-relation-departed")
def lb_departed():
   config["lb-ready"] = False

@hooks.hook("update-status")
def update_status():
  set_status()
  #status_set("active", "Unit ready")

def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log("Unknown hook {} - skipping.".format(e))

if __name__ == "__main__":
    main()