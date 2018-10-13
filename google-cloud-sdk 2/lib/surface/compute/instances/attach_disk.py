# -*- coding: utf-8 -*- #
# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Command for attaching a disk to an instance."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from googlecloudsdk.api_lib.compute import base_classes
from googlecloudsdk.api_lib.compute import csek_utils
from googlecloudsdk.api_lib.compute import instance_utils
from googlecloudsdk.calliope import base
from googlecloudsdk.command_lib.compute import scope as compute_scopes
from googlecloudsdk.command_lib.compute.instances import flags

MODE_OPTIONS = {
    'ro': 'Read-only.',
    'rw': (
        'Read-write. It is an error to attach a disk in read-write mode to '
        'more than one instance.'),
}

DETAILED_HELP = {
    'DESCRIPTION': """\
        *{command}* is used to attach a disk to an instance. For example,

          $ gcloud compute instances attach-disk example-instance --disk DISK --zone us-central1-a

        attaches the disk named 'DISK' to the instance named
        'example-instance' in zone ``us-central1-a''.

        After you create and attach a new disk to an instance, you must
        [format and mount](https://cloud.google.com/compute/docs/disks/add-persistent-disk#formatting)
        the disk so that the operating system can use the available storage
        space.
        """,
}


def _Args(parser,
          support_disk_scope=False,
          support_force_attach=False,
          support_boot=False):
  """Add parser arguments to all tracks."""

  flags.INSTANCE_ARG.AddArgument(parser)

  # TODO(b/69955187): Add note about matching with name in order to mount to
  # container.
  parser.add_argument(
      '--device-name',
      help=('An optional name that indicates the disk name the guest '
            'operating system will see. (Note: Device name does not '
            'correspond to mounted volume name). Must match the disk name '
            'if the disk is going to be mounted to a container with '
            '--container-mount-disk (alpha feature).'))

  parser.add_argument(
      '--disk',
      help='The name of the disk to attach to the instance.',
      required=True)

  parser.add_argument(
      '--mode',
      choices=MODE_OPTIONS,
      default='rw',
      help='Specifies the mode of the disk.')

  if support_disk_scope:
    flags.AddDiskScopeFlag(parser)

  if support_force_attach:
    parser.add_argument(
        '--force-attach',
        default=False,
        action='store_true',
        help="""\
Attach the disk to the instance even if it is currently attached to another
instance. The attachment will succeed even if detaching from the previous
instance fails at first. The server will continue trying to detach the disk from
the previous instance in the background.""")

  if support_boot:
    parser.add_argument(
        '--boot',
        action='store_true',
        help='Attach the disk to the instance as a boot disk.')

  csek_utils.AddCsekKeyArgs(parser, flags_about_creation=False)


@base.ReleaseTracks(base.ReleaseTrack.GA)
class AttachDisk(base.SilentCommand):
  """Attach a disk to an instance."""

  @staticmethod
  def Args(parser):
    _Args(parser)

  # This function should be overridden by subclasses to customize disk resource
  # creation as necessary for alpha release track.
  def ParseDiskRef(self, resources, args, instance_ref):
    return instance_utils.ParseDiskResource(resources, args.disk,
                                            instance_ref.project,
                                            instance_ref.zone,
                                            compute_scopes.ScopeEnum.ZONE)

  def Run(self, args):
    """Invokes a request for attaching a disk to an instance."""
    holder = base_classes.ComputeApiHolder(self.ReleaseTrack())
    client = holder.client

    instance_ref = flags.INSTANCE_ARG.ResolveAsResource(
        args, holder.resources,
        scope_lister=flags.GetInstanceZoneScopeLister(client))

    disk_ref = self.ParseDiskRef(holder.resources, args, instance_ref)

    if args.mode == 'rw':
      mode = client.messages.AttachedDisk.ModeValueValuesEnum.READ_WRITE
    else:
      mode = client.messages.AttachedDisk.ModeValueValuesEnum.READ_ONLY

    allow_rsa_encrypted = self.ReleaseTrack() in [base.ReleaseTrack.ALPHA,
                                                  base.ReleaseTrack.BETA]
    csek_keys = csek_utils.CsekKeyStore.FromArgs(args, allow_rsa_encrypted)
    disk_key_or_none = csek_utils.MaybeLookupKeyMessage(csek_keys, disk_ref,
                                                        client.apitools_client)

    attached_disk = client.messages.AttachedDisk(
        deviceName=args.device_name,
        mode=mode,
        source=disk_ref.SelfLink(),
        type=client.messages.AttachedDisk.TypeValueValuesEnum.PERSISTENT,
        diskEncryptionKey=disk_key_or_none)

    if self.ReleaseTrack() == base.ReleaseTrack.ALPHA and args.boot:
      attached_disk.boot = args.boot

    request = client.messages.ComputeInstancesAttachDiskRequest(
        instance=instance_ref.Name(),
        project=instance_ref.project,
        attachedDisk=attached_disk,
        zone=instance_ref.zone)

    if self.ReleaseTrack() in (base.ReleaseTrack.ALPHA, base.ReleaseTrack.BETA):
      request.forceAttach = args.force_attach

    return client.MakeRequests([(client.apitools_client.instances, 'AttachDisk',
                                 request)])


@base.ReleaseTracks(base.ReleaseTrack.BETA)
class AttachDiskBeta(AttachDisk):
  """Attach a disk to an instance."""

  @staticmethod
  def Args(parser):
    _Args(
        parser,
        support_disk_scope=True,
        support_force_attach=True)

  def ParseDiskRef(self, resources, args, instance_ref):
    if args.disk_scope == 'regional':
      scope = compute_scopes.ScopeEnum.REGION
    else:
      scope = compute_scopes.ScopeEnum.ZONE
    return instance_utils.ParseDiskResource(resources, args.disk,
                                            instance_ref.project,
                                            instance_ref.zone,
                                            scope)


@base.ReleaseTracks(base.ReleaseTrack.ALPHA)
class AttachDiskAlpha(AttachDiskBeta):
  """Attach a disk to an instance."""

  @staticmethod
  def Args(parser):
    _Args(
        parser,
        support_disk_scope=True,
        support_force_attach=True,
        support_boot=True)


AttachDisk.detailed_help = DETAILED_HELP