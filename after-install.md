# XMPP plugin installed

Two more steps to finish the install.

1. Finish setup (tool-progress display default and optional avatar):

   ```
   python3 ~/.hermes/plugins/xmpp-platform/post_install.py
   ```

2. Restart the gateway:

   ```
   hermes gateway restart
   ```

Upgrades later: `hermes plugins update xmpp-platform` then `hermes gateway restart`.
