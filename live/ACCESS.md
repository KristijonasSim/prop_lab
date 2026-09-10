# Getting at the bot from another machine

Written 2026-09-10. Kris will be on a different PC over the weekend.

**No credential is committed to this repo, and none should be.** Git history is
permanent: a key pushed once is in every clone and every fork forever, and
deleting it later does not remove it from the history. The VM key in particular
opens a box that is running the previous project's live bot.

## The good news: you probably need nothing

**The bot runs on the VM, not on any PC.** Cron fires it hourly, it holds its own
leg book, and the exchange holds a backstop stop. You do not need this repo, the
Bybit keys, or a laptop for it to keep trading. Turning every PC off changes
nothing.

## To WATCH it — SSH only, and that key already syncs between your PCs

The key lives in the OTHER repo, which is where it has always lived and which
already ships it to both machines:

    ~/trading-bots/bybit_bot/deploy/ssh/oracle_bots

On the other PC:

    git clone <trading-bots remote> ~/trading-bots
    chmod 600 ~/trading-bots/bybit_bot/deploy/ssh/oracle_bots
    KEY=~/trading-bots/bybit_bot/deploy/ssh/oracle_bots

    # what has it done
    ssh -i $KEY ubuntu@89.168.78.138 'tail -40 ~/prop_lab/live/paper/bybit_cron.log'
    # what does it think it holds
    ssh -i $KEY ubuntu@89.168.78.138 'cat ~/prop_lab/live/paper/bybit_state.json'
    # is cron still alive
    ssh -i $KEY ubuntu@89.168.78.138 'crontab -l; systemctl is-active cron'

## To STOP it

    ssh -i $KEY ubuntu@89.168.78.138 'crontab -r'

That stops new decisions. It does **not** close the open position: the exchange
keeps the backstop stop and the position stays until it is closed by hand or the
bot runs again.

## To see the account without any key at all

Log into Bybit in a browser, switch to **Demo Trading**, open XAUUSDT. The
position, the stop and the P&L are all there. That is the fastest check and it
needs nothing installed.

## If you really do need the API keys elsewhere

They live outside the repo at `~/.config/prop_lab/bybit_demo.env`. Three ways to
carry them, in order of preference:

1. **Regenerate on the other PC.** Bybit → API → create a new demo key. Thirty
   seconds, and the old one can be revoked.
2. **A password manager**, copied by hand into
   `~/.config/prop_lab/bybit_demo.env` with `chmod 600`.
3. `scp` them from this machine while it is on.

**Do not paste them into a chat again** - the current pair went through one on
2026-09-10 and should be rotated regardless.

## DO NOT run the bot on two machines

The leg book (`live/paper/bybit_state.json`) is what stops it re-opening
positions it already holds, and it lives on whichever machine runs the bot. Two
copies running means two books, and the second one opens the entire six-leg book
again on top of the first. **The VM owns it.** There is deliberately no crontab
entry on Kris's desktop.
