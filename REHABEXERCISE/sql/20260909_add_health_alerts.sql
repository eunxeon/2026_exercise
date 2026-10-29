-- Non-destructive migration: add guardian-visible health alerts.
-- Existing ElderlyUsers, GuardianUserLinks, and ExerciseRecords data is preserved.

IF OBJECT_ID('dbo.HealthAlerts', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.HealthAlerts (
        alert_id BIGINT IDENTITY(1,1) NOT NULL,
        user_id NVARCHAR(64) NOT NULL,
        alert_type NVARCHAR(64) NOT NULL,
        severity NVARCHAR(24) NOT NULL,
        title NVARCHAR(120) NOT NULL,
        message NVARCHAR(1000) NOT NULL,
        overall_status NVARCHAR(32) NOT NULL,
        source_rom_record_id BIGINT NULL,
        source_exercise_record_ids NVARCHAR(128) NOT NULL
            CONSTRAINT DF_HealthAlerts_source_exercise_record_ids DEFAULT (N'[]'),
        is_read BIT NOT NULL
            CONSTRAINT DF_HealthAlerts_is_read DEFAULT (0),
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_HealthAlerts_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_HealthAlerts
            PRIMARY KEY (alert_id),
        CONSTRAINT FK_HealthAlerts_ElderlyUsers
            FOREIGN KEY (user_id) REFERENCES dbo.ElderlyUsers(user_id)
    );
END
GO

IF OBJECT_ID('dbo.HealthAlerts', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.HealthAlerts', 'source_exercise_record_ids') IS NULL
BEGIN
    ALTER TABLE dbo.HealthAlerts
    ADD source_exercise_record_ids NVARCHAR(128) NOT NULL
        CONSTRAINT DF_HealthAlerts_source_exercise_record_ids DEFAULT (N'[]');
END
GO

IF OBJECT_ID('dbo.HealthAlerts', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.HealthAlerts', 'is_read') IS NULL
BEGIN
    ALTER TABLE dbo.HealthAlerts
    ADD is_read BIT NOT NULL
        CONSTRAINT DF_HealthAlerts_is_read DEFAULT (0);
END
GO

IF OBJECT_ID('dbo.HealthAlerts', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.HealthAlerts', 'created_at') IS NULL
BEGIN
    ALTER TABLE dbo.HealthAlerts
    ADD created_at DATETIME2 NOT NULL
        CONSTRAINT DF_HealthAlerts_created_at DEFAULT SYSUTCDATETIME();
END
GO

IF OBJECT_ID('dbo.FK_HealthAlerts_ElderlyUsers', 'F') IS NULL
    AND OBJECT_ID('dbo.HealthAlerts', 'U') IS NOT NULL
    AND OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.HealthAlerts
    ADD CONSTRAINT FK_HealthAlerts_ElderlyUsers
        FOREIGN KEY (user_id) REFERENCES dbo.ElderlyUsers(user_id);
END
GO

IF OBJECT_ID('dbo.HealthAlerts', 'U') IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID('dbo.HealthAlerts')
            AND name = 'IX_HealthAlerts_duplicate_source'
    )
BEGIN
    CREATE INDEX IX_HealthAlerts_duplicate_source
    ON dbo.HealthAlerts (
        user_id,
        overall_status,
        source_rom_record_id,
        source_exercise_record_ids
    );
END
GO

IF OBJECT_ID('dbo.HealthAlerts', 'U') IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID('dbo.HealthAlerts')
            AND name = 'IX_HealthAlerts_user_created'
    )
BEGIN
    CREATE INDEX IX_HealthAlerts_user_created
    ON dbo.HealthAlerts (user_id, created_at DESC, alert_id DESC);
END
GO
