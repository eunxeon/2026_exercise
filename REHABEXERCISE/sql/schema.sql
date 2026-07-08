IF OBJECT_ID('dbo.ExerciseRecords', 'U') IS NOT NULL DROP TABLE dbo.ExerciseRecords;
IF OBJECT_ID('dbo.MirrorDevices', 'U') IS NOT NULL DROP TABLE dbo.MirrorDevices;
IF OBJECT_ID('dbo.Exercises', 'U') IS NOT NULL DROP TABLE dbo.Exercises;
IF OBJECT_ID('dbo.ElderlyUsers', 'U') IS NOT NULL DROP TABLE dbo.ElderlyUsers;
GO

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
        CONSTRAINT DF_MirrorDevices_updated_at DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.ElderlyUsers (
    user_id NVARCHAR(64) NOT NULL PRIMARY KEY,
    name NVARCHAR(80) NOT NULL,
    birth_year INT NULL,
    memo NVARCHAR(500) NULL,
    created_at DATETIME2 NOT NULL
        CONSTRAINT DF_ElderlyUsers_created_at DEFAULT SYSUTCDATETIME()
);
GO

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
GO

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
GO

ALTER TABLE dbo.MirrorDevices
ADD CONSTRAINT FK_MirrorDevices_ElderlyUsers
    FOREIGN KEY (paired_user_id) REFERENCES dbo.ElderlyUsers(user_id);
GO

-- TODO: In the next phase, insert one ExerciseRecords row when a training session
-- starts, then update accuracy_avg, feedback_summary, and ended_at on completion.
