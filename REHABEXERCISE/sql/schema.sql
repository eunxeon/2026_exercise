-- Non-destructive schema setup for the smart mirror prototype.
-- Existing tables and data are preserved; missing tables/constraints are created.

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ElderlyUsers (
        user_id NVARCHAR(64) NOT NULL PRIMARY KEY,
        name NVARCHAR(80) NOT NULL,
        birth_year INT NULL,
        gender NVARCHAR(20) NULL,
        birth_date DATE NULL,
        height_cm DECIMAL(5,2) NULL,
        weight_kg DECIMAL(5,2) NULL,
        health_condition NVARCHAR(500) NULL,
        memo NVARCHAR(500) NULL,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_ElderlyUsers_created_at DEFAULT SYSUTCDATETIME()
    );
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'gender') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD gender NVARCHAR(20) NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'birth_date') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD birth_date DATE NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'height_cm') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD height_cm DECIMAL(5,2) NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'weight_kg') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD weight_kg DECIMAL(5,2) NULL;
END
GO

IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
    AND COL_LENGTH('dbo.ElderlyUsers', 'health_condition') IS NULL
BEGIN
    ALTER TABLE dbo.ElderlyUsers
    ADD health_condition NVARCHAR(500) NULL;
END
GO

IF OBJECT_ID('dbo.Exercises', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Exercises (
        exercise_key NVARCHAR(64) NOT NULL PRIMARY KEY,
        title NVARCHAR(120) NOT NULL,
        category NVARCHAR(80) NOT NULL,
        description NVARCHAR(1000) NULL,
        video_path NVARCHAR(255) NULL,
        is_supported BIT NOT NULL
            CONSTRAINT DF_Exercises_is_supported DEFAULT (0),
        status_label NVARCHAR(40) NOT NULL
            CONSTRAINT DF_Exercises_status_label DEFAULT (N'준비 중')
    );
END
GO

IF OBJECT_ID('dbo.MirrorDevices', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.MirrorDevices (
        mirror_id NVARCHAR(64) NOT NULL PRIMARY KEY,
        device_name NVARCHAR(120) NOT NULL,
        pairing_code NVARCHAR(16) NULL,
        pairing_status NVARCHAR(24) NOT NULL
            CONSTRAINT DF_MirrorDevices_pairing_status DEFAULT ('waiting'),
        paired_user_id NVARCHAR(64) NULL,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_MirrorDevices_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL
            CONSTRAINT DF_MirrorDevices_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_MirrorDevices_ElderlyUsers
            FOREIGN KEY (paired_user_id) REFERENCES dbo.ElderlyUsers(user_id)
    );
END
GO

IF OBJECT_ID('dbo.ExerciseRecords', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ExerciseRecords (
        record_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        user_id NVARCHAR(64) NOT NULL,
        exercise_key NVARCHAR(64) NOT NULL,
        accuracy_avg DECIMAL(5,2) NULL,
        feedback_summary NVARCHAR(1000) NULL,
        started_at DATETIME2 NOT NULL,
        ended_at DATETIME2 NULL,
        CONSTRAINT FK_ExerciseRecords_ElderlyUsers
            FOREIGN KEY (user_id) REFERENCES dbo.ElderlyUsers(user_id),
        CONSTRAINT FK_ExerciseRecords_Exercises
            FOREIGN KEY (exercise_key) REFERENCES dbo.Exercises(exercise_key)
    );
END
GO

IF OBJECT_ID('dbo.GuardianAccounts', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.GuardianAccounts (
        guardian_id NVARCHAR(64) NOT NULL,
        login_id NVARCHAR(80) NOT NULL,
        password_hash NVARCHAR(255) NOT NULL,
        name NVARCHAR(80) NOT NULL,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_GuardianAccounts_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL
            CONSTRAINT DF_GuardianAccounts_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_GuardianAccounts
            PRIMARY KEY (guardian_id),
        CONSTRAINT UQ_GuardianAccounts_login_id
            UNIQUE (login_id)
    );
END
GO

IF OBJECT_ID('dbo.GuardianUserLinks', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.GuardianUserLinks (
        guardian_id NVARCHAR(64) NOT NULL,
        user_id NVARCHAR(64) NOT NULL,
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_GuardianUserLinks_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_GuardianUserLinks
            PRIMARY KEY (guardian_id, user_id),
        CONSTRAINT FK_GuardianUserLinks_GuardianAccounts
            FOREIGN KEY (guardian_id) REFERENCES dbo.GuardianAccounts(guardian_id),
        CONSTRAINT FK_GuardianUserLinks_ElderlyUsers
            FOREIGN KEY (user_id) REFERENCES dbo.ElderlyUsers(user_id)
    );
END
GO

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

IF OBJECT_ID('dbo.UQ_GuardianAccounts_login_id', 'UQ') IS NULL
    AND OBJECT_ID('dbo.GuardianAccounts', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.GuardianAccounts
    ADD CONSTRAINT UQ_GuardianAccounts_login_id
        UNIQUE (login_id);
END
GO

IF OBJECT_ID('dbo.PK_GuardianUserLinks', 'PK') IS NULL
    AND OBJECT_ID('dbo.GuardianUserLinks', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.GuardianUserLinks
    ADD CONSTRAINT PK_GuardianUserLinks
        PRIMARY KEY (guardian_id, user_id);
END
GO

IF OBJECT_ID('dbo.FK_GuardianUserLinks_GuardianAccounts', 'F') IS NULL
    AND OBJECT_ID('dbo.GuardianUserLinks', 'U') IS NOT NULL
    AND OBJECT_ID('dbo.GuardianAccounts', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.GuardianUserLinks
    ADD CONSTRAINT FK_GuardianUserLinks_GuardianAccounts
        FOREIGN KEY (guardian_id) REFERENCES dbo.GuardianAccounts(guardian_id);
END
GO

IF OBJECT_ID('dbo.FK_GuardianUserLinks_ElderlyUsers', 'F') IS NULL
    AND OBJECT_ID('dbo.GuardianUserLinks', 'U') IS NOT NULL
    AND OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.GuardianUserLinks
    ADD CONSTRAINT FK_GuardianUserLinks_ElderlyUsers
        FOREIGN KEY (user_id) REFERENCES dbo.ElderlyUsers(user_id);
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

IF OBJECT_ID('dbo.FK_MirrorDevices_ElderlyUsers', 'F') IS NULL
    AND OBJECT_ID('dbo.MirrorDevices', 'U') IS NOT NULL
    AND OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.MirrorDevices
    ADD CONSTRAINT FK_MirrorDevices_ElderlyUsers
        FOREIGN KEY (paired_user_id) REFERENCES dbo.ElderlyUsers(user_id);
END
GO

IF OBJECT_ID('dbo.FK_ExerciseRecords_ElderlyUsers', 'F') IS NULL
    AND OBJECT_ID('dbo.ExerciseRecords', 'U') IS NOT NULL
    AND OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.ExerciseRecords
    ADD CONSTRAINT FK_ExerciseRecords_ElderlyUsers
        FOREIGN KEY (user_id) REFERENCES dbo.ElderlyUsers(user_id);
END
GO

IF OBJECT_ID('dbo.FK_ExerciseRecords_Exercises', 'F') IS NULL
    AND OBJECT_ID('dbo.ExerciseRecords', 'U') IS NOT NULL
    AND OBJECT_ID('dbo.Exercises', 'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.ExerciseRecords
    ADD CONSTRAINT FK_ExerciseRecords_Exercises
        FOREIGN KEY (exercise_key) REFERENCES dbo.Exercises(exercise_key);
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
