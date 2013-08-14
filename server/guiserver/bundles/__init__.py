# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2013 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Juju GUI server bundles support.

Note that the following is a work in progress. Some of the objects described
below are not yet implemented.

This package includes the objects and functions required to support deploying
bundles in juju-core. The base pieces of the infrastructure are placed in the
base module:

    - base.Deployer: any object implementing the following interface:
        - validate(user, name, bundle) -> Future (str or None);
        - import_bundle(user, name, bundle) -> int (a deployment id);
        - watch(deployment_id) -> int or None (a watcher id);
        - next(watcher_id) -> Future (changes or None).

      The following arguments are passed to the validate and import_bundle
      interface methods:
        - user: a guiserver.auth.User instance, representing a logged in user;
        - name: a string representing the name of the bundle to be imported;
        - bundle: a YAML decoded object representing the bundle contents.
      The watch and next interface methods are used to retrieve information
      about the status of the currently started/scheduled deployments.

      The Deployer provides the logic to validate deployment requests based on
      the current state of the Juju environment, to import bundles, and to
      observe the deployment process. The Deployer does not know anything about
      the WebSocket request/response aspects, or how incoming data is retrieved
      or generated.

      The Deployer implementation in this module uses the juju-deployer library
      to import the provided bundle into the Juju environment. Since the
      mentioned operations are executed in a separate process, it is safe for
      the Deployer to interact with the blocking juju-deployer library.
      Those blocking functions are defined in the blocking module of this
      package, described below.

      Note that the Deployer is not intended to store request related data: one
      instance is created once when the application is bootstrapped and used as
      a singleton by all WebSocket requests;

    - base.DeployMiddleware: process deployment requests arriving from the
      client, validate the requests' data and send the appropriate responses.
      Since the bundles deployment protocol (described below) mimics the usual
      request/response paradigm over a WebSocket, the real request handling
      is delegated by the DeployMiddleware to simple functions present in the
      views module of this package. The DeployMiddleware dispatches requests
      and collect responses to be sent back to the API client.

The views and blocking modules are responsible of handling the request/response
process and of starting/scheduling bundle deployments.

    - views: as already mentioned, the functions in this module handle the
      requests from the API client, and set up responses. Since the views have
      access to the Deployer (described above), they can start/queue bundle
      deployments.

    - blocking: all the blocking functions interacting with the juju-deployer
      library belong here. Specifically this module defines two function:
        - validate: validate a bundle based on the state of the Juju env.;
        - import_bundle: starts the bundle deployment process.

The infrastructure described above can be summarized like the following
(each arrow meaning "calls"):
    - request handling: request -> DeployMiddleware -> views
    - deployment handling: views -> Deployer -> blocking
    - response handling: views -> response

While the DeployMiddleware parses the request data and statically validates
that it is well formed, the Deployer takes care of validating the request in
the context of the current Juju environment.

Importing a bundle.
-------------------

A deployment request looks like the following:

    {
        'RequestId': 1,
        'Type': 'Deployer',
        'Request': 'Import',
        'Params': {'Name': 'bundle-name', 'YAML': 'bundles'},
    }

In the future it will be possible to pass "URL" in place of "YAML" in order to
deploy a bundle from a URL.

After receiving a deployment request, the DeployMiddleware sends a response
indicating whether or not the request has been accepted. This response is sent
relatively quickly.

If the request is not valid, the response looks like the following:

    {
        'RequestId': 1,
        'Response': {},
        'Error': 'some error: error details',
    }


If instead the request is valid, the response is like this:

    {
        'RequestId': 1,
        'Response': {'DeploymentId': 42},
    }

The deployment identifier can be used later to observe the progress and status
of the deployment (see below).

Watching a deployment progress.
-------------------------------

To start observing the progress of a specific deployment, the client must send
a watch request like the following:

    {
        'RequestId': 2,
        'Type': 'Deployer',
        'Request': 'Watch',
        'Params': {'DeploymentId': 42},
    }

If any error occurs, the response is like this:

    {
        'RequestId': 2,
        'Response': {},
        'Error': 'some error: error details',
    }

Otherwise, the response includes the watcher identifier to use to actually
retrieve deployment events, e.g.:

    {
        'RequestId': 2,
        'Response': {'WatcherId': 42},
    }

Use the watcher id to retrieve changes:

    {
        'RequestId': 3,
        'Type': 'Deployer',
        'Request': 'Next',
        'Params': {'WatcherId': 47},
    }

As usual, if an error occurs, the error description will be included in the
response:

    {
        'RequestId': 3,
        'Response': {},
        'Error': 'some error: error details',
    }

If everything is ok, a response is sent as soon as any unseen deployment change
becomes available, e.g.:

    {
        'RequestId': 3,
        'Response': {
            'Changes': [
                {'DeploymentId': 42, 'Status': 'scheduled', 'Queue': 2},
                {'DeploymentId': 42, 'Status': 'scheduled', 'Queue': 1},
                {'DeploymentId': 42, 'Status': 'started', 'Queue': 0},
            ],
        },
    }

The Queue values in the response indicates the position of the requested
bundle deployment in the queue. The Deployer implementation processes one
bundle at the time. A Queue value of zero means the deployment will be started
as soon as possible.

The Status can be one of the following: 'scheduled', 'started' and 'completed'.

The Next request can be performed as many times as required by the API clients
after receiving a response from a previous one. However, if the Status of the
last deployment change is 'completed', no further changes will be notified, and
the watch request will always return only the last change:

    {
        'RequestId': 4,
        'Response': {
            'Changes': [
                {
                  'DeploymentId': 42,
                  'Status': 'completed',
                  'Error': 'this field is only present if an error occurred',
                },
            ],
        },
    }

XXX frankban: a timeout to delete completed deployments history will be
eventually implemented.

Deployments status.
-------------------

To retrieve the current status of all the active/scheduled bundle deployments,
the client can send the following request:

    {
        'RequestId': 5,
        'Type': 'Deployer',
        'Request': 'Status',
    }

In the two examples below, the first one represents a response with errors,
the second one is a successful response:

    {
        'RequestId': 5,
        'Response': {},
        'Error': 'some error: error details',
    }

    {
        'RequestId': 5,
        'Response': {
            'LastChanges': [
                {'DeploymentId': 42, 'Status': 'completed', 'Error': 'error'},
                {'DeploymentId': 43, 'Status': 'completed'},
                {'DeploymentId': 44, 'Status': 'started', 'Queue': 0},
                {'DeploymentId': 45, 'Status': 'scheduled', 'Queue': 1},
            ],
        },
    }

In the second response above, the Error field in the first attempted deployment
(42) contains details about an error that occurred while deploying a bundle.
This means that bundle deployment has been completed but an error occurred
during the process.
"""
