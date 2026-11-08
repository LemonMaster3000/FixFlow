# FixFlow account, invitation and team update

## What's changed

- Registration now has mutually exclusive Student, Faculty and Other account-type choices. These are radio choices, not independent checkboxes, because only one account type can apply.
- Every account registers with a full name, email address and password.
- Student accounts additionally require an institution and enrollment number. Enrollment numbers are unique within an institution and are searchable only inside that institution.
- Faculty accounts additionally require an institution.
- Other accounts require only name, email and password and receive a separate personal workspace so their institutional records are not shared with unrelated Other users.
- People registering with the same institution name (case-insensitive match) join the same FixFlow organization.
- Connections now sends invitations to registered accounts. Student invitations use enrollment number within the sender's institution; Faculty and Other invitations use the registered email address.
- Recipients can accept or reject connection invitations. Both sides see accepted connections and senders can see pending/rejected status.
- Team creation is available to signed-in users. The creator is leader. Team invitations use student enrollment number or email for Faculty/Other. Acceptance adds the recipient to the team as a member, visible to both accounts.
- SMTP email delivery is supported through environment variables. Without SMTP configuration, invitations still appear in the recipient's in-app notifications and invitation inbox.

## Apply to an existing installation

1. Stop Flask with `Ctrl+C`.
2. Back up the entire existing project folder and database.
3. Extract this ZIP into the existing project folder and overwrite application files.
4. Do not delete `fixflow.db` or the `instance` folder. Startup adds the account-type and enrollment-number columns plus a filtered unique enrollment index without deleting existing records.
5. Install dependencies if needed: `pip install -r requirements.txt`.
6. Restart with `python app.py` and test registration, connection invitations, and team invitations using two separate accounts.

## SMTP setup for actual email delivery

Configure these environment variables on the hosting service (for Gmail use a Google App Password, not the normal account password):

- `MAIL_SERVER=smtp.gmail.com`
- `MAIL_PORT=587`
- `MAIL_USERNAME=your-sending-address@gmail.com`
- `MAIL_PASSWORD=your-google-app-password`
- `MAIL_DEFAULT_SENDER=your-sending-address@gmail.com`
- `APP_BASE_URL=https://your-deployed-fixflow-domain`

Never commit SMTP credentials to source code or put them in the ZIP. Without these variables, FixFlow does not claim an email was sent; the invitation remains available in-app.

## Important deployment and data notes

- Institution names must match for accounts to join the same organization. Use the institution's consistent official name during registration.
- Student enrollment numbers are unique per institution, not globally across every institution.
- Student invitations search only the sender's institution. Faculty/Other invitations match exact registered email.
- The invitation email links to the recipient's FixFlow invitation inbox. The recipient must sign in to accept or reject.
- This update does not implement email ownership verification, password reset, or an external identity-provider login. Do not treat an unverified email address as proof of identity for production deployment. Add email verification before opening registration publicly.
- Existing account records remain intact. Existing accounts receive the default account type `Other` until profile editing is added; existing organization membership and administrator roles are unchanged. New registrations receive the ordinary member role. Provision an institution administrator separately, rather than automatically granting admin rights to the first student or faculty registrant.
- Full browser and production database testing must be completed before deployment. Flask dependencies were not installed in the build environment, so runtime integration tests could not be run here.
