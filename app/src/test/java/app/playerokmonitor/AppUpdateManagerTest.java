package app.playerokmonitor;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class AppUpdateManagerTest {
    @Test
    public void semanticVersionsAreComparedNumerically() {
        assertEquals(1, AppUpdateManager.compareVersions("2.3.18", "2.3.17"));
        assertEquals(-1, AppUpdateManager.compareVersions("2.9.9", "2.10.0"));
        assertEquals(0, AppUpdateManager.compareVersions("2.3.18", "2.3.18"));
    }

    @Test
    public void malformedVersionCannotMasqueradeAsAnUpdate() {
        assertEquals(-1, AppUpdateManager.compareVersions("not-a-version", "2.3.18"));
    }
}
