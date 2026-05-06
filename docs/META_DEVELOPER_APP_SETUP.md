# Meta Developer App Setup

1. Go to `https://developers.facebook.com/apps` and create a Meta app.

2. In the app dashboard, add the Instagram Graph API product.

3. Link the Facebook Page that owns your Instagram Business account:

   - Open Facebook Page settings.
   - Connect the Instagram account.
   - Confirm the Instagram account is a Business or Creator account.

4. Generate a long-lived Instagram access token with these permissions:

   ```text
   instagram_basic
   instagram_manage_comments
   pages_read_engagement
   ```

   Use Graph API Explorer or your app's OAuth flow. Exchange the short-lived token for a long-lived token before placing it in `.env`.

5. Get your Instagram Business Account ID:

   ```http
   GET https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_TOKEN
   GET https://graph.facebook.com/v19.0/{page-id}?fields=instagram_business_account&access_token=YOUR_TOKEN
   ```

   Use the returned `instagram_business_account.id` value as `IG_BUSINESS_ID`.

6. Register the webhook in the Meta app dashboard:

   - Callback URL: `https://your-public-domain.com/webhook`
   - Verify token: the same value as `IG_VERIFY_TOKEN`
   - Subscribe to the `mentions` field for Instagram.

7. Complete App Review if Meta requires it for production access to the permissions or webhook fields.

8. Before launch, use the dashboard webhook tester and confirm your server returns `200 OK`.
