-- Idempotent demo guardian seed for Android presentation/testing.
-- This script does not create or modify ElderlyUsers, ExerciseRecords,
-- MirrorDevices, or Exercises.

DECLARE @guardian_id NVARCHAR(64) = N'guardian-demo-001';
DECLARE @login_id NVARCHAR(80) = N'demo_guardian';
DECLARE @password_hash NVARCHAR(255) = CONVERT(NVARCHAR(255), SESSION_CONTEXT(N'DEMO_GUARDIAN_PASSWORD_HASH'));
IF NULLIF(@password_hash, N'') IS NULL
BEGIN
    THROW 50001, 'Set DEMO_GUARDIAN_PASSWORD_HASH in this SQL session before running the demo seed.', 1;
END;

DECLARE @name NVARCHAR(80) = N'데모 보호자';
DECLARE @user_id NVARCHAR(64) = N'user-1';
DECLARE @effective_guardian_id NVARCHAR(64);

SELECT @effective_guardian_id = guardian_id
FROM dbo.GuardianAccounts
WHERE login_id = @login_id;

IF @effective_guardian_id IS NULL
BEGIN
    SET @effective_guardian_id = @guardian_id;

    IF NOT EXISTS (
        SELECT 1
        FROM dbo.GuardianAccounts
        WHERE guardian_id = @guardian_id
    )
    BEGIN
        INSERT INTO dbo.GuardianAccounts (
            guardian_id,
            login_id,
            password_hash,
            name,
            created_at,
            updated_at
        )
        VALUES (
            @guardian_id,
            @login_id,
            @password_hash,
            @name,
            SYSUTCDATETIME(),
            SYSUTCDATETIME()
        );
    END
    ELSE
    BEGIN
        UPDATE dbo.GuardianAccounts
        SET login_id = @login_id,
            password_hash = @password_hash,
            name = @name,
            updated_at = SYSUTCDATETIME()
        WHERE guardian_id = @guardian_id;
    END
END
ELSE
BEGIN
    UPDATE dbo.GuardianAccounts
    SET password_hash = @password_hash,
        name = @name,
        updated_at = SYSUTCDATETIME()
    WHERE guardian_id = @effective_guardian_id;
END

IF EXISTS (
    SELECT 1
    FROM dbo.ElderlyUsers
    WHERE user_id = @user_id
)
AND NOT EXISTS (
    SELECT 1
    FROM dbo.GuardianUserLinks
    WHERE guardian_id = @effective_guardian_id
        AND user_id = @user_id
)
BEGIN
    INSERT INTO dbo.GuardianUserLinks (guardian_id, user_id, created_at)
    VALUES (@effective_guardian_id, @user_id, SYSUTCDATETIME());
END
GO
