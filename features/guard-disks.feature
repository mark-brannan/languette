@python
Feature: guard-disks
  The commands that overwrite a disk are denied.
  mkfs, wipefs and shred pass on an image file in the agent's own area
  (the scratchpad, an agent worktree, /tmp); the rest have no such area.
  The working directory is {CWD}, a directory outside $HOME, unless a
  scenario says otherwise; {UP} is the ../ for each of its levels.

  Scenario Outline: writing onto a device is denied, however it is spelled
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                                | naming                       | note                                       |
      | dd if=disk.img of=/dev/sda             | is a device node             |                                            |
      | dd if=x of=/dev/nvme0n1p2 bs=4M        | is a device node             |                                            |
      | sudo dd if=x of=/dev/disk2             | is a device node             |                                            |
      | dd of=/dev/../dev/sda                  | is a device node             | a .. segment is applied, not trusted       |
      | dd of=/dev/mapper/vg-root if=x         | is a device node             | any node under /dev that is not a sink     |
      | dd if=x of=$DEV                        | glob, brace or variable      | an unresolved target could be a device     |
      | dd if=x of="$DEV"                      | glob, brace or variable      |                                            |
      | dd if=x of=/dev/sd?                    | glob, brace or variable      |                                            |
      | sh -c 'dd if=x of=/dev/sda'            | is a device node             | nested text is scanned                     |
      | echo x > /dev/sda                      | writes onto a disk device    | redirection                                |
      | cat disk.img > /dev/nvme0n1            | writes onto a disk device    |                                            |
      | echo x >> /dev/mmcblk0                 | writes onto a disk device    | append                                     |
      | echo x 2> /dev/sdb                     | writes onto a disk device    | a file-descriptor redirect                 |
      | echo x &> /dev/sdb                     | writes onto a disk device    |                                            |
      | echo x >\|/dev/sda                     | writes onto a disk device    | clobber                                    |
      | echo x >"/dev/sda"                     | writes onto a disk device    | quoted                                     |
      | cat disk.img \| tee /dev/sda           | writes onto a disk device    | tee                                        |
      | cat disk.img \| sudo tee -a /dev/vda   | writes onto a disk device    |                                            |
      | sh -c 'cat disk.img > /dev/sda'        | writes onto a disk device    | nested text is scanned                     |
      | cat disk.img > /dev//sda               | writes onto a disk device    | the path is judged as the filesystem sees it |
      | cat disk.img > /dev/./sda              | writes onto a disk device    |                                            |
      | cat disk.img > /tmp/../dev/sda         | writes onto a disk device    |                                            |
      | cat disk.img > {UP}dev/sda             | writes onto a disk device    | relative to the working directory          |
      | cat disk.img \| tee /dev//sda          | writes onto a disk device    | tee is judged the same way                 |
      | cat disk.img \| tee /tmp/../dev/sda    | writes onto a disk device    |                                            |
      | echo x > /dev/mem                      | writes onto a disk device    | memory and RAM devices                     |
      | echo x \| tee /dev/kmem                | writes onto a disk device    |                                            |
      | echo x > /dev/zram0                    | writes onto a disk device    |                                            |

  Scenario Outline: a relative path after a cd that may land in /dev cannot be followed, so it is denied
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                 | verdict                                     | note                                   |
      | cd /dev && cat disk.img > sda           | denies, naming "`cd` earlier"               | a redirect                             |
      | cd /dev; echo x \| tee sda              | denies, naming "`cd` earlier"               | tee                                    |
      | cd /dev && dd if=x of=sda               | denies, naming "`cd` earlier"               | dd                                     |
      | pushd /dev/disk && cat x > by-id/y      | denies, naming "`cd` earlier"               | pushd                                  |
      | cd {UP}dev && cat x > sda               | denies, naming "`cd` earlier"               | a relative cd that lands in /dev       |
      | cd "$D" && cat x > sda                  | denies, naming "`cd` earlier"               | a cd the hook cannot resolve           |
      | cd - && cat x > sda                     | denies, naming "`cd` earlier"               |                                        |
      | popd && cat x > sda                     | denies, naming "`cd` earlier"               |                                        |
      | env -C /dev dd if=x of=sda              | denies, naming "`cd` earlier"               | env -C changes the directory too       |
      | sudo -D /dev tee sda                    | denies, naming "`cd` earlier"               | sudo -D                                |
      | env -C/dev dd if=x of=sda               | denies, naming "`cd` earlier"               | the value attached                     |
      | sudo -nD /dev tee sda                   | denies, naming "`cd` earlier"               | a short cluster                        |
      | sudo -u root tee sda                    | is silent                                   | -u takes root as its value             |
      | cd /dev && cat x > /dev/sda             | denies, naming "writes onto a disk device"  | an absolute path is still judged       |
      | cd /dev && cat x > /tmp/out             | is silent                                   | an absolute path outside /dev          |
      | cd build && echo x > out.log            | is silent                                   | a cd that lands elsewhere              |
      | cd /tmp && dd if=a of=out.bin           | is silent                                   |                                        |
      | cd sub && echo x \| tee out.txt         | is silent                                   |                                        |
      | cd && echo x > notes.txt                | is silent                                   | cd with no operand is $HOME            |

  Scenario Outline: mkfs, wipefs and shred are denied on anything but the agent's own area
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                                    | naming                                       | note                                    |
      | mkfs.ext4 /dev/sdb1                        | is a device node                             |                                         |
      | mkfs -t ext4 /dev/sdb1                     | is a device node                             | -t takes a value                        |
      | sudo mkfs.vfat -F 32 /dev/mmcblk0p1        | is a device node                             |                                         |
      | mkswap /dev/sda2                           | is a device node                             |                                         |
      | mke2fs -L data /dev/sdc                    | is a device node                             |                                         |
      | mkfs.ext4 disk.img                         | outside the scratchpad, /tmp and agent worktrees | a file in the project is the user's |
      | mkfs.ext4 -F -L data ~/disk.img            | outside the scratchpad, /tmp and agent worktrees |                                     |
      | mkfs.ext4                                  | no device or image file is visible           |                                         |
      | mkfs.ext4 -F "$IMG"                        | variable or command substitution             |                                         |
      | mkfs.ext4 /tmp/a.img /dev/sda              | is a device node                             | one target the user's is enough         |
      | wipefs -a /dev/sda                         | is a device node                             |                                         |
      | wipefs -a ~/disk.img                       | outside the scratchpad, /tmp and agent worktrees |                                     |
      | shred -vfz /dev/sda                        | is a device node                             |                                         |
      | shred -u ~/secrets.txt                     | outside the scratchpad, /tmp and agent worktrees |                                     |
      | shred -n 3 notes.txt                       | outside the scratchpad, /tmp and agent worktrees | -n takes a value, notes.txt is the target |
      | shred                                      | no target is visible                         |                                         |
      | ls \| xargs shred                          | no target is visible                         |                                         |
      | shred *.txt                                | glob or brace expansion                      |                                         |
      | shred ../x                                 | `..` segment                                 |                                         |
      | cd x && shred y                            | `cd` earlier                                 |                                         |

  Scenario Outline: the denial names the safe path
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                    | naming                                             |
      | dd if=x of=/dev/sda        | Work on an image file in /tmp or the scratchpad    |
      | mkfs.ext4 /dev/sdb1        | hand them the exact command                        |
      | echo x > /dev/sda          | hand them the exact command                        |

  Scenario Outline: an image file in the agent's own area, a device that is only read, and anything that does not write a disk
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | cwd            | command                                          | note                                           |
      | {HOME}/project | dd if=/dev/zero of=/dev/null bs=1M count=100     | /dev/null is a sink                            |
      | {HOME}/project | dd if=/dev/urandom of=/tmp/x.img bs=1M count=1   | an image file in /tmp                          |
      | {HOME}/project | dd if=/dev/sda of=disk.img                       | reading a device is not writing it             |
      | {HOME}/project | dd if=a of=out.bin                               | a regular file                                 |
      | {HOME}/project | dd if=a of=/dev/stdout                           |                                                |
      | {HOME}/project | dd if=a of=/dev/fd/3                             |                                                |
      | {HOME}/project | echo x > /dev/null                               |                                                |
      | {HOME}/project | ls 2> /dev/null                                  |                                                |
      | {HOME}/project | echo x 2>&1 >/dev/null                           | a dup, then a sink                             |
      | {HOME}/project | echo x > /dev/stderr                             |                                                |
      | {HOME}/project | echo x > /dev/shm/x                              | tmpfs, not a disk                              |
      | {HOME}/project | echo x > /tmp/../tmp/x                           | a .. that lands in /tmp                        |
      | {HOME}/project | cat /dev/sda \| head -c 512 > /tmp/mbr           | read a device, write /tmp                      |
      | {HOME}/project | ls /dev/sda                                      |                                                |
      | {HOME}/project | mkfs.ext4 -F /tmp/disk.img                       | an image file in /tmp                          |
      | {HOME}/project | mkfs.ext4 -F -L data /tmp/disk.img 1024          | a label and a block count                      |
      | {HOME}/project | mkfs -t ext4 {HOME}/.local/state/claude-tmpdir/x.img | the scratchpad                              |
      | {HOME}/project | mkswap {HOME}/.claude/worktrees/w/swap.img       | an agent worktree                              |
      | {HOME}/project | wipefs /tmp/disk.img                             |                                                |
      | {HOME}/project | shred -u /tmp/scratch.txt                        |                                                |
      | {HOME}/project | shred -n 3 -z /tmp/a /tmp/b                      |                                                |
      | /tmp           | shred -u scratch.txt                             | relative to /tmp                               |
      | {HOME}/project | echo "x > /dev/sda"                              | a quoted mention of a redirection              |
      | {HOME}/project | git commit -m "dd of=/dev/sda"                   |                                                |

  Scenario: a target is judged where its symlinks lead
    Given the symlink "{TMP}/escape" to "{HOME}"
    When the agent runs `shred -u {TMP}/escape/secrets.txt`
    Then the guard denies, naming "resolves through a symlink"
