# The demo bot on the VM

Written 2026-09-10. Kris: *"i will leave this pc turned off and turn on only on
monday… i think its worth to launch it"*. It runs on the Oracle VM from the
previous project.

    host    ubuntu@89.168.78.138        Ubuntu 20.04, x86_64, 2 cores, 952MB
    key     ~/trading-bots/bybit_bot/deploy/ssh/oracle_bots   (chmod 600)
    path    ~/prop_lab                  code only - no data, no backtests
    python  ~/opt/python/bin/python3    3.12.11, standalone build
    cron    2 * * * *                   one pass per closed 1h bar, at :02

**A bot from the old project already runs on this box** (`bot-n5.service`).
Nothing here touches it: the standalone Python is unpacked under `~/opt`, the
system's 3.8 and 3.9 are untouched, and the cron entry is additive.

## Why a standalone Python and not apt

Ubuntu 20.04 has 3.8 and 3.9; this repo needs 3.12. The deadsnakes PPA is added
on the box and **its focal package index is empty** - they have dropped 20.04, so
`apt install python3.12` cannot work no matter how the sources are written.
Building from source on 2 cores and 952MB is slow and leaves build deps behind.
The `python-build-standalone` tarball is a prebuilt 3.12.11, unpacks in seconds,
needs no root and changes nothing outside `~/opt`.

## The versions are pinned to the local venv, deliberately

    numpy 2.5.2   pandas 2.3.3   numba 0.67.0   llvmlite 0.49.0

Installing `numba==0.67.0` pulls numpy **down to 2.3.5**, so numpy is re-pinned
afterwards. The signal is arithmetic on cumulative sums and a different numpy is
unlikely to change it - but "unlikely" is not a thing to leave in a bot that
places orders, and matching the versions costs one pip command.

## THE HANDOFF THAT NEARLY WENT WRONG

The five VWAP legs and the Asian leg live in `live/paper/bybit_state.json`, and
the first rsync **excluded `live/paper`**. The VM's dry run said `book: 0 legs`
while the exchange showed a 3.669 XAU short: arming it there would have opened
the whole book a second time on top of the existing position.

**Only one machine may run this bot at a time, and whichever one runs it must
hold the current leg book.** The state file was copied across before the VM was
armed, and the local crontab was deliberately NOT installed.

    scp -i $KEY live/paper/bybit_state.json ubuntu@89.168.78.138:~/prop_lab/live/paper/

## Watch it

    KEY=~/trading-bots/bybit_bot/deploy/ssh/oracle_bots
    ssh -i $KEY ubuntu@89.168.78.138 'tail -30 ~/prop_lab/live/paper/bybit_cron.log'
    ssh -i $KEY ubuntu@89.168.78.138 'cat ~/prop_lab/live/paper/bybit_state.json'

## Stop it

    ssh -i $KEY ubuntu@89.168.78.138 'crontab -r'

That stops new decisions. It does NOT close the open position - the exchange
still holds the backstop stop, and the position stays until it is closed by hand
or the bot is started again.

## Update the code after a change here

    rsync -az --delete --exclude .git --exclude .venv --exclude data \
      --exclude backtests --exclude notebooks --exclude '__pycache__' \
      --exclude live/paper -e "ssh -i $KEY" ./ ubuntu@89.168.78.138:~/prop_lab/

`live/paper` is excluded on purpose: the VM's leg book is the live one and must
never be overwritten by this machine's copy.
